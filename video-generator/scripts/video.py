#!/usr/bin/env python3
"""Local caption-timed videos, extracted from the La Tienda Python/Kokoro/FFmpeg workflow."""
import argparse
import array
import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

HERE = Path(__file__).resolve().parent


def run(args, **kwargs):
    r = subprocess.run([str(x) for x in args], capture_output=True, **kwargs)
    if r.returncode:
        raise RuntimeError(f"{args[0]} failed:\n{r.stderr.decode(errors='replace')[-5000:]}")
    return r


def key(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()[:24]


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2) + '\n')


def timestamp(seconds):
    n = round(seconds * 1000)
    return f'{n//3600000:02}:{n//60000%60:02}:{n//1000%60:02},{n%1000:03}'


def read_srt(path):
    cues = []
    for block in re.split(r'\n\s*\n', Path(path).read_text().strip()):
        lines = block.splitlines()
        def seconds(t):
            h, m, s = t.replace(',', '.').split(':')
            return int(h) * 3600 + int(m) * 60 + float(s)
        a, b = lines[1].split(' --> ')
        cues.append(dict(start=seconds(a), end=seconds(b), text='\n'.join(lines[2:])))
    return cues


def write_srt(path, cues):
    Path(path).write_text('\n\n'.join(f"{i+1}\n{timestamp(c['start'])} --> {timestamp(c['end'])}\n{c['caption']}"
                                     for i, c in enumerate(cues)) + '\n')


def probe(path):
    return json.loads(run(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', path]).stdout)


def font_path(name):
    p = Path(name).expanduser()
    if p.exists():
        return str(p.resolve())
    return run(['fc-match', '-f', '%{file}', name]).stdout.decode().strip()


def load(project, output):
    project = Path(project).resolve()
    c = json.loads(project.read_text())
    c.setdefault('title', 'Project walkthrough')
    for k, v in dict(width=1280, height=720, fps=24, max_duration=120, pause=.3,
                     motion='zoom', transition_seconds=.18, caption_mode='burn').items():
        c.setdefault(k, v)
    c['voice'] = {**dict(voice='af_heart', speed=.95, language='en-us', model_dir='~/tools/kokoro-tts'), **c.get('voice', {})}
    c['theme'] = {**dict(background='#FFF8F0', ink='#41171E', accent='#EE641E', muted='#765F60',
                        font='Open Sans', heading_font='Montserrat:style=Bold'), **c.get('theme', {})}
    if any(not isinstance(c[x], int) for x in ['width', 'height', 'fps']):
        raise ValueError('width, height and fps must be integers')
    if c['width'] < 640 or c['height'] < 360 or c['width'] % 2 or c['height'] % 2 or not 1 <= c['fps'] <= 60:
        raise ValueError('Use even dimensions >=640x360 and fps between 1 and 60')
    if c['motion'] not in ['none', 'zoom'] or c['caption_mode'] not in ['burn', 'soft', 'none']:
        raise ValueError('Invalid motion or caption_mode')
    if c['pause'] < 0 or c['transition_seconds'] < 0 or c['max_duration'] <= 0:
        raise ValueError('Durations must be positive; pause and transition may be zero')
    if not c.get('scenes'):
        raise ValueError('At least one scene is required')
    for scene in c['scenes']:
        scene.setdefault('title', c['title'])
        if not scene.get('narration'):
            raise ValueError('Each scene needs narration cues')
        for k in ['html', 'image']:
            if scene.get(k):
                scene[k] = str((project.parent / Path(scene[k]).expanduser()).resolve())
        scene['narration'] = [dict(text=t, caption=t) if isinstance(t, str) else
                              dict(text=t['text'], caption=t.get('caption', t['text'])) for t in scene['narration']]
        if any(not t['text'].strip() or not t['caption'].strip() for t in scene['narration']):
            raise ValueError('Narration and captions cannot be empty')
    out = Path(output).resolve()
    out.mkdir(parents=True, exist_ok=True)
    return c, out


def text_signature(c):
    return key([[t['text'] for t in s['narration']] for s in c['scenes']])


def timeline(c, out):
    m = json.loads((out / 'timeline.json').read_text())
    if (m['text_signature'] != text_signature(c) or m['fps'] != c['fps'] or
        m['timing_config'] != key([c['voice'],c['pause'],c.get('target_duration')])):
        raise ValueError('Narration text/fps changed; run narrate first')
    for cue in m['cues']:
        cue['caption'] = c['scenes'][cue['scene']]['narration'][cue['cue']]['caption']
    return m


def audio(c, out):
    v = c['voice']
    model = Path(v['model_dir']).expanduser().resolve()
    python = Path(v.get('python', model / '.venv/bin/python')).expanduser()
    files = [model / 'kokoro-v1.0.onnx', model / 'voices-v1.0.bin']
    for p in [python, *files]:
        if not p.exists():
            raise FileNotFoundError(f'Missing {p}; no automatic model/package downloads')
    identity = [(str(p), p.stat().st_size, p.stat().st_mtime_ns) for p in files]
    tasks, cues = [], []
    for i, scene in enumerate(c['scenes']):
        for j, t in enumerate(scene['narration']):
            sig = key([t['text'], v, identity, sha(HERE / 'narrate.py')])
            dest = out / 'audio' / f'{sig}.wav'
            tasks.append(dict(id=f'{i+1}.{j+1}', text=t['text'], output=str(dest)))
            cues.append(dict(scene=i, cue=j, caption=t['caption'], audio=str(dest)))
    request = out / 'audio-request.json'
    save(request, dict(model_dir=str(model), voice=v['voice'], speed=v['speed'],
                       language=v['language'], threads=v.get('threads', 4), tasks=tasks))
    r = run([python, HERE / 'narrate.py', request])
    print(r.stdout.decode(), end='')
    pieces, rate, natural = [], None, 0
    for cue in cues:
        with wave.open(cue['audio'], 'rb') as w:
            if w.getnchannels() != 1 or w.getsampwidth() != 2:
                raise ValueError('Expected mono 16-bit Kokoro audio')
            if rate is not None and rate != w.getframerate():
                raise ValueError('Mixed sample rates')
            rate = w.getframerate()
            raw = w.readframes(w.getnframes())
        cue['speech_seconds'] = len(raw) / (2 * rate)
        cue['frames'] = math.ceil((cue['speech_seconds'] + c['pause']) * c['fps'])
        pieces.append(raw)
        natural += cue['frames'] / c['fps']
    target = c.get('target_duration', natural)
    if target + .001 < natural:
        raise ValueError(f'Natural narration needs {natural:.2f}s, exceeding target {target}s; shorten script, not the requested voice speed')
    if target > c['max_duration'] + .001:
        raise ValueError('target_duration exceeds max_duration')
    extra = math.ceil((target - natural) * c['fps'])
    for i in range(extra):
        cues[i % len(cues)]['frames'] += 1
    total = sum(x['frames']/c['fps'] for x in cues)
    if total > c['max_duration'] + .001:
        raise ValueError(f'Narration is {total:.2f}s, above max_duration {c["max_duration"]}s; shorten the script or explicitly change the limit')
    elapsed = 0
    with wave.open(str(out / 'narration.wav'), 'wb') as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(rate)
        for cue, raw in zip(cues, pieces):
            duration = cue['frames'] / c['fps']
            cue.update(start=elapsed, end=elapsed + duration)
            elapsed += duration
            samples = round(duration * rate)
            w.writeframes(raw + b'\0\0' * (samples - len(raw) // 2))
    save(out / 'timeline.json', dict(text_signature=text_signature(c), timing_config=key([c['voice'],c['pause'],c.get('target_duration')]), fps=c['fps'],
                                     duration=elapsed, sample_rate=rate, voice=v, cues=cues))
    print(f'Narration timeline: {elapsed:.3f}s')


def wrap(draw, text, font, width):
    lines = []
    for paragraph in text.splitlines() or ['']:
        line = ''
        for word in paragraph.split():
            if draw.textlength(word, font=font) > width:
                raise ValueError(f'Word too wide for layout: {word[:35]}')
            trial = (line + ' ' + word).strip()
            if line and draw.textlength(trial, font=font) > width:
                lines.append(line); line = word
            else:
                line = trial
        lines.append(line)
    return lines


def poster(c, scene, out):
    from PIL import Image, ImageDraw, ImageFont
    w, h, theme = c['width'], c['height'], c['theme']
    if scene.get('image'):
        external = sha(scene['image'])
    elif scene.get('html'):
        # Hash the self-contained HTML; linked local assets require a fresh filename or HTML edit.
        external = sha(scene['html'])
    else:
        external = None
    sig = key([w, h, theme, {k:v for k,v in scene.items() if k != 'narration'}, external,
               sha(HERE / 'video.py')])
    target = out / 'posters' / f'{sig}.png'
    target.parent.mkdir(exist_ok=True)
    if target.exists():
        return target
    if scene.get('html'):
        chrome = c.get('chromium') or shutil.which('chromium') or shutil.which('google-chrome')
        if not chrome:
            raise FileNotFoundError('Chromium/Chrome is needed only for an HTML scene')
        with tempfile.TemporaryDirectory(prefix='video-chromium-') as profile:
            run([chrome, '--headless', '--disable-gpu', '--no-first-run', '--no-default-browser-check',
                 f'--user-data-dir={profile}', '--hide-scrollbars', '--force-device-scale-factor=1',
                 f'--window-size={w},{h}', f'--virtual-time-budget={scene.get("html_time_ms", 500)}',
                 f'--screenshot={target}', Path(scene['html']).as_uri()])
        with Image.open(target) as image:
            if image.size != (w, h):
                raise ValueError('HTML screenshot dimensions differ from configuration')
        return target
    if scene.get('image'):
        with Image.open(scene['image']) as image:
            if image.size != (w, h):
                raise ValueError('Provide an image at exact configured dimensions; no silent cropping')
            image.convert('RGB').save(target)
        return target
    scale = w / 1280
    image = Image.new('RGB', (w, h), theme['background'])
    d = ImageDraw.Draw(image)
    margin = int(w * .045)
    regular, bold = font_path(theme['font']), font_path(theme['heading_font'])
    def text(value, x, y, size, width, color, weight=False, bottom=None):
        font = ImageFont.truetype(bold if weight else regular, max(12, round(size * scale)))
        lines = wrap(d, value, font, width)
        step = round(size * scale * 1.32)
        if bottom is not None and y + len(lines) * step > bottom:
            raise ValueError('Text overflows slide; shorten it or change layout')
        for line in lines:
            d.text((x, y), line, font=font, fill=color); y += step
    d.rectangle((0,0,w,max(4,round(8*scale))), fill=theme['accent'])
    text(c.get('brand', c['title']).upper(), margin, int(h*.045), 20, w-2*margin, theme['ink'], True, h*.15)
    text(scene.get('kicker','').upper(), margin, int(h*.18), 17, w-2*margin, theme['accent'], True, h*.25)
    text(scene['title'], margin, int(h*.255), 38, w-2*margin, theme['ink'], True, h*.41)
    cards = scene.get('cards', [])
    if not 1 <= len(cards) <= 3:
        raise ValueError('Default layout needs 1–3 cards; use an image or HTML for custom layouts')
    gap = int(w*.026); cw = (w-2*margin-gap*(len(cards)-1)) // len(cards)
    top, bottom = int(h*.45), int(h*.76)
    for i, card in enumerate(cards):
        x = margin+i*(cw+gap)
        d.rounded_rectangle((x,top,x+cw,bottom),radius=max(6,round(16*scale)),fill='white',outline='#E8D9CF',width=2)
        d.rectangle((x,top,x+max(3,round(5*scale)),bottom),fill=theme['accent'])
        pad = round(22*scale)
        text(card['title'],x+pad,top+pad,26,cw-2*pad,theme['ink'],True,top+int(h*.105))
        text(card.get('body',''),x+pad,top+int(h*.12),21,cw-2*pad,theme['muted'],False,bottom-pad)
    if scene.get('footer'):
        text(scene['footer'],margin,int(h*.80),20,w-2*margin,theme['muted'],False,h*.86)
    image.save(target)
    return target


def encode_flags():
    enc = run(['ffmpeg','-hide_banner','-encoders']).stdout.decode()
    if 'libx264' in enc:
        return ['-c:v','libx264','-preset','fast','-crf','19']
    if 'libopenh264' in enc:
        return ['-c:v','libopenh264','-b:v','3000k']
    raise RuntimeError('FFmpeg needs libx264 or libopenh264 for compatible H.264 MP4')


def visual_config_key(c):
    scenes = [{k:v for k,v in s.items() if k!='narration'} for s in c['scenes']]
    assets = [sha(s[k]) for s in scenes for k in ['image','html'] if s.get(k)]
    return key([c['width'],c['height'],c['fps'],c['theme'],c['motion'],c['transition_seconds'],scenes,assets])


def schedule_key(m):
    return key([(x['scene'], x['frames']) for x in m['cues']])


def visuals(c, out):
    m = timeline(c, out)
    clips = []
    for scene_i, scene in enumerate(c['scenes']):
        image = poster(c, scene, out)
        for cue in [x for x in m['cues'] if x['scene']==scene_i]:
            duration = cue['end']-cue['start']
            sig = key([sha(image),cue['frames'],c['fps'],c['motion'],c['transition_seconds']])
            clip = out / 'clips' / f'{sig}.mp4'; clip.parent.mkdir(exist_ok=True)
            if not clip.exists():
                if c['motion']=='zoom':
                    filters = [f"zoompan=z='1+0.025*on/{max(cue['frames']-1,1)}':x='iw/2-iw/zoom/2':y='ih/2-ih/zoom/2':d={cue['frames']}:s={c['width']}x{c['height']}:fps={c['fps']}"]
                else:
                    filters = [f'fps={c["fps"]}']
                fade = min(c['transition_seconds'],duration/4)
                if fade:
                    filters += [f'fade=t=in:st=0:d={fade}',f'fade=t=out:st={duration-fade}:d={fade}']
                run(['ffmpeg','-hide_banner','-loglevel','error','-y','-loop','1','-i',image,
                     '-vf',','.join(filters),'-frames:v',str(cue['frames']),'-an',*encode_flags(),
                     '-pix_fmt','yuv420p',clip])
            clips.append(clip)
    listing = out / 'clips.ffconcat'
    listing.write_text('ffconcat version 1.0\n'+''.join(f"file 'clips/{p.name}'\n" for p in clips))
    run(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','concat','-safe','1','-i',listing,'-c:v','copy','-an',out/'visuals.mp4'])
    save(out/'visuals.json', dict(schedule=schedule_key(m),config_key=visual_config_key(c),sha256=sha(out/'visuals.mp4')))


def captions(c, out):
    from PIL import Image, ImageDraw, ImageFont
    m = timeline(c,out)
    write_srt(out/'captions.srt',m['cues'])
    # ASS in pixel coordinates reserves the same readable caption band as the original videos.
    w,h = c['width'],c['height']; size = max(18,round(w*32/1280)); lineheight = size*1.4
    d = ImageDraw.Draw(Image.new('RGB',(w,h)))
    f = ImageFont.truetype(font_path(c['theme']['font']),size)
    header = f'''[Script Info]\nScriptType: v4.00+\nPlayResX: {w}\nPlayResY: {h}\nWrapStyle: 2\n[V4+ Styles]\nFormat: Name,Fontname,Fontsize,PrimaryColour,SecondaryColour,OutlineColour,BackColour,Bold,Italic,Underline,StrikeOut,ScaleX,ScaleY,Spacing,Angle,BorderStyle,Outline,Shadow,Alignment,MarginL,MarginR,MarginV,Encoding\nStyle: Default,{c['theme']['font']},{size},&H00FFFFFF,&H00FFFFFF,&H001E1741,&H001E1741,0,0,0,0,100,100,0,0,1,1,0,2,{round(w*.045)},{round(w*.045)},{round(h*.04)},1\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n'''
    def ass_time(t):
        n=round(t*100);return f'{n//360000}:{n//6000%60:02}:{n//100%60:02}.{n%100:02}'
    rows=[]
    for cue in m['cues']:
        lines=wrap(d,cue['caption'],f,w*.90)
        if len(lines)*lineheight > h*.17:
            raise ValueError('Caption exceeds safe band; split the narration cue or shorten caption text')
        # Escape untrusted ASS controls; no arbitrary style/tag injection.
        text='\\N'.join(s.replace('\\','/').replace('{','(').replace('}',')') for s in lines)
        rows.append(f"Dialogue: 0,{ass_time(cue['start'])},{ass_time(cue['end'])},Default,,0,0,0,,{text}\n")
    (out/'captions.ass').write_text(header+''.join(rows))


def mux(c,out):
    m=timeline(c,out)
    v=json.loads((out/'visuals.json').read_text())
    if v['schedule'] != schedule_key(m) or v['config_key'] != visual_config_key(c) or v['sha256'] != sha(out/'visuals.mp4'):
        raise ValueError('Visual timeline is stale; run visuals before mux')
    if c['caption_mode']!='none':
        captions(c,out)
    # Relative filter filenames avoid shell/filter escaping of spaces, colons and apostrophes in paths.
    args=['ffmpeg','-hide_banner','-loglevel','error','-y','-i','visuals.mp4','-i','narration.wav']
    if c['caption_mode']=='soft': args+=['-i','captions.srt']
    args+=['-map','0:v:0','-map','1:a:0']
    if c['caption_mode']=='burn':
        band=round(c['height']*.19)
        args+=['-vf',f"drawbox=x=0:y=ih-{band}:w=iw:h={band}:color=0x41171E:t=fill,ass=captions.ass",*encode_flags(),'-pix_fmt','yuv420p']
    else: args+=['-c:v','copy']
    if c['caption_mode']=='soft': args+=['-map','2:s:0','-c:s','mov_text','-disposition:s:0','default']
    args+=['-c:a','aac','-b:a','160k','-af','loudnorm=I=-18:TP=-1.5:LRA=11','-t',str(m['duration']),'-movflags','+faststart','video.tmp.mp4']
    run(args,cwd=out)
    (out/'video.tmp.mp4').replace(out/'video.mp4')
    save(out/'render.json',dict(config_key=key(c),video_sha256=sha(out/'video.mp4'),timeline_sha256=sha(out/'timeline.json'),
                               narration_sha256=sha(out/'narration.wav'),caption_mode=c['caption_mode'],width=c['width'],height=c['height']))


def validate(c,out):
    from PIL import Image,ImageDraw
    m=timeline(c,out);info=probe(out/'video.mp4')
    release=json.loads((out/'render.json').read_text())
    if (release['config_key'] != key(c) or release['timeline_sha256'] != sha(out/'timeline.json') or
        release['narration_sha256'] != sha(out/'narration.wav') or release['video_sha256'] != sha(out/'video.mp4')):
        raise ValueError('Final video is stale or changed; run mux before validate')
    v=next(x for x in info['streams'] if x['codec_type']=='video')
    a=next(x for x in info['streams'] if x['codec_type']=='audio')
    if v['codec_name']!='h264' or a['codec_name']!='aac' or (v['width'],v['height'])!=(c['width'],c['height']):
        raise ValueError('Incorrect codecs or dimensions')
    duration=float(info['format']['duration'])
    if abs(duration-m['duration'])>.15 or duration>c['max_duration']+.15:
        raise ValueError('Duration does not match narration timeline or limit')
    if abs(float(v.get('duration',duration))-float(a.get('duration',duration)))>.15:
        raise ValueError('Audio/video duration mismatch')
    if c['caption_mode']!='none':
        cues=read_srt(out/'captions.srt')
        if len(cues)!=len(m['cues']):raise ValueError('Caption count mismatch')
        for i,(x,y) in enumerate(zip(cues,m['cues'])):
            if abs(x['start']-y['start'])>.002 or abs(x['end']-y['end'])>.002 or x['text']!=y['caption']:
                raise ValueError('Caption timing or text mismatch')
            if x['end']<=x['start'] or (i and x['start']<cues[i-1]['end']-.002):
                raise ValueError('Non-monotonic captions')
            if y['speech_seconds']>y['end']-y['start']+.002:raise ValueError('Caption ends before speech')
    with wave.open(str(out/'narration.wav'),'rb') as w:
        samples=array.array('h'); samples.frombytes(w.readframes(w.getnframes()))
        if sys.byteorder!='little':samples.byteswap()
    rms=math.sqrt(sum(x*x for x in samples)/len(samples))/32768
    if rms<.0001:raise ValueError('Narration is silent')
    run(['ffmpeg','-hide_banner','-v','error','-i',out/'video.mp4','-f','null','-'])
    rows=math.ceil(len(c['scenes'])/2);sheet=Image.new('RGB',(960,rows*270),'#E8D9CF')
    for i in range(len(c['scenes'])):
        cue=next(x for x in m['cues'] if x['scene']==i)
        frame=out/f'check-{i+1:02}.png'
        run(['ffmpeg','-hide_banner','-v','error','-y','-ss',str((cue['start']+cue['end'])/2),'-i',out/'video.mp4','-frames:v','1','-update','1',frame])
        with Image.open(frame) as image:sheet.paste(image.resize((480,270)),((i%2)*480,(i//2)*270))
    sheet.save(out/'contact-sheet.jpg')
    save(out/'verification.json',dict(duration=duration,video_codec=v['codec_name'],audio_codec=a['codec_name'],
             width=v['width'],height=v['height'],narration_rms=rms,captions_checked=len(m['cues']),
             full_decode_passed=True,human_listening_review=False,video_sha256=sha(out/'video.mp4')))
    print(f'Verified {out/"video.mp4"}: {duration:.3f}s')


def doctor():
    model=Path('~/tools/kokoro-tts').expanduser()
    result=dict(python=sys.version.split()[0],tools={x:shutil.which(x) for x in
                ['ffmpeg','ffprobe','fc-match','chromium','google-chrome']},
                kokoro={str(p):p.exists() for p in [model/'.venv/bin/python',model/'kokoro-v1.0.onnx',model/'voices-v1.0.bin']})
    try:
        import PIL
        result['pillow']=PIL.__version__
    except ImportError:result['pillow']=None
    print(json.dumps(result,indent=2))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('stage',choices=['doctor','all','narrate','captions','visuals','mux','validate'])
    p.add_argument('--project');p.add_argument('--out')
    args=p.parse_args()
    if args.stage=='doctor':return doctor()
    if not args.project or not args.out:p.error('--project and --out required')
    c,out=load(args.project,args.out)
    stages=dict(narrate=audio,captions=captions,visuals=visuals,mux=mux,validate=validate)
    for stage in (['narrate','captions','visuals','mux','validate'] if args.stage=='all' else [args.stage]):
        stages[stage](c,out)


if __name__=='__main__':
    try:main()
    except (ValueError,RuntimeError,FileNotFoundError) as error:
        sys.exit(str(error))
