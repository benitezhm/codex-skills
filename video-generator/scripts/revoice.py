#!/usr/bin/env python3
"""Replace narration of an existing captioned MP4; preserve source, script and visuals.
Derived from the working La Tienda Kokoro replacement, not a general video editor.
"""
import argparse
import json
import re
import sys
import wave
from pathlib import Path
from PIL import Image, ImageChops, ImageStat
import video


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',required=True);p.add_argument('--srt',required=True)
    p.add_argument('--output',required=True);p.add_argument('--voice',default='af_heart')
    p.add_argument('--speed',type=float,default=.95);p.add_argument('--language',default='en-us')
    p.add_argument('--model-dir',default='~/tools/kokoro-tts')
    p.add_argument('--keep-timing',action='store_true',help='Copy video stream; fail if speech cannot fit source cue slots')
    args=p.parse_args()
    source=Path(args.source).resolve();srt=Path(args.srt).resolve();dest=Path(args.output).resolve()
    if dest in [source,srt] or dest.exists():raise ValueError('Output must be a new path; original is never overwritten')
    cues=video.read_srt(srt);info=video.probe(source)
    v=next(x for x in info['streams'] if x['codec_type']=='video')
    if v['codec_name']!='h264':raise ValueError('This remux/revoice helper expects an H.264 source MP4')
    for i,c in enumerate(cues):
        if c['end']<=c['start'] or (i==0 and c['start']>.05) or (i and abs(c['start']-cues[i-1]['end'])>.05):
            raise ValueError('Provide contiguous caption cues from time zero; general timeline editing is outside this helper')
    fps_num,fps_den=map(int,v['r_frame_rate'].split('/'));fps=fps_num/fps_den
    if abs(fps-round(fps))>.0001:raise ValueError('This helper currently supports constant integer frame rates only')
    fps=round(fps);original_hash=video.sha(source);srt_hash=video.sha(srt)
    work=dest.parent/(dest.stem+'.work');work.mkdir(parents=True,exist_ok=True)
    config=dict(title='Voice replacement',fps=fps,width=v['width'],height=v['height'],max_duration=86400,
                voice=dict(voice=args.voice,speed=args.speed,language=args.language,model_dir=args.model_dir),
                scenes=[dict(title='Preserved source',narration=[x['text'] for x in cues])])
    video.save(work/'project.json',config);c,out=video.load(work/'project.json',work)
    video.audio(c,out);m=video.timeline(c,out)
    source_duration=float(v.get('duration',info['format']['duration']))
    if abs(cues[-1]['end']-source_duration)>.2:
        raise ValueError('Caption coverage does not match source video duration')
    # Recover exact encoded caption boundaries, as in the proven replacement script.
    if not args.keep_timing:
        r=video.run(['ffmpeg','-hide_banner','-i',source,'-vf',"select='gt(scene,0.0003)',showinfo",'-an','-f','null','-'])
        changes=[float(x) for x in re.findall(r'pts_time:([0-9.]+)',r.stderr.decode())]
        starts=[0.0]
        for cue in cues[1:]:
            if not changes:raise ValueError('No visible cuts found; supply matching cue boundaries or use --keep-timing')
            t=min(changes,key=lambda x:abs(x-cue['start']))
            if abs(t-cue['start'])>.2:raise ValueError('Cannot reliably match a caption cut; original left unchanged')
            starts.append(round(t*fps)/fps)
        starts.append(source_duration)
        if any(b<=a for a,b in zip(starts,starts[1:])):raise ValueError('Ambiguous or duplicate caption boundaries')
        clips=[]
        for i,cue in enumerate(m['cues']):
            clip=work/f'retimed-{i:03}.mp4';duration=cue['end']-cue['start'];orig=starts[i+1]-starts[i]
            video.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-ss',str(starts[i]),'-t',str(orig),'-i',source,
                       '-an','-vf',f'setpts={duration/orig}*(PTS-STARTPTS),fps={fps},tpad=stop_mode=clone:stop_duration=1',
                       '-frames:v',str(cue['frames']),*video.encode_flags(),'-pix_fmt','yuv420p',clip])
            clips.append(clip)
        listing=work/'retimed.ffconcat';listing.write_text('ffconcat version 1.0\n'+''.join(f"file '{p.name}'\n" for p in clips))
        visual_args=['-f','concat','-safe','1','-i',listing]
    else:
        # The normal generated WAVs are unpadded; fit each into its original source slot.
        with wave.open(str(work/'narration.wav'),'wb') as output:
            output.setnchannels(1);output.setsampwidth(2);output.setframerate(m['sample_rate'])
            for i,cue in enumerate(m['cues']):
                start=cues[i]['start'];end=cues[i+1]['start'] if i+1<len(cues) else source_duration
                with wave.open(cue['audio'],'rb') as w:raw=w.readframes(w.getnframes())
                samples=round(end*m['sample_rate'])-round(start*m['sample_rate'])
                if len(raw)//2>samples:raise ValueError(f'Speech cue {i+1} will not fit; use retiming instead')
                output.writeframes(raw+b'\0\0'*(samples-len(raw)//2));cue.update(start=start,end=end)
        m['duration']=source_duration;visual_args=['-i',source];starts=[x['start'] for x in cues]+[source_duration]
    # -n protects prior outputs, even if another process creates the path while rendering.
    video.run(['ffmpeg','-hide_banner','-loglevel','error','-n',*visual_args,'-i',work/'narration.wav',
               '-map','0:v:0','-map','1:a:0','-c:v','copy','-c:a','aac','-b:a','160k',
               '-af','loudnorm=I=-18:TP=-1.5:LRA=11','-t',str(m['duration']),'-movflags','+faststart',dest])
    video.write_srt(dest.with_suffix('.srt'),m['cues'])
    video.run(['ffmpeg','-hide_banner','-v','error','-i',dest,'-f','null','-'])
    checked=video.probe(dest)
    if abs(float(checked['format']['duration'])-m['duration'])>.15:raise ValueError('Output duration mismatch')
    def frame(path,t):
        raw=video.run(['ffmpeg','-hide_banner','-v','error','-ss',str(t),'-i',path,'-frames:v','1',
                       '-f','rawvideo','-pix_fmt','rgb24','pipe:1']).stdout
        return Image.frombytes('RGB',(v['width'],v['height']),raw)
    differences=[]
    for i,cue in enumerate(m['cues']):
        a=frame(source,(starts[i]+starts[i+1])/2);b=frame(dest,(cue['start']+cue['end'])/2)
        delta=sum(ImageStat.Stat(ImageChops.difference(a,b)).mean)/3
        # Frame comparison is informative for motion; not a pixel-equality promise.
        differences.append(delta)
    if video.sha(source)!=original_hash or video.sha(srt)!=srt_hash:raise ValueError('Source was modified unexpectedly')
    video.save(work/'verification.json',dict(source_sha256=original_hash,source_unchanged=True,
                caption_source_unchanged=True,full_decode_passed=True,duration=m['duration'],voice=c['voice'],
                source_clip_midpoint_differences=differences,human_listening_review=False))
    print(f'Created {dest}; original and caption source unchanged')


if __name__=='__main__':
    try:main()
    except (ValueError,RuntimeError,FileNotFoundError) as error:sys.exit(str(error))
