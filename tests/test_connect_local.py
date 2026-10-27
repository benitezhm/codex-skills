"""Isolated tests: no real user instructions or installed skills are changed."""
import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location('connect_local', Path(__file__).parents[1]/'scripts/connect_local.py')
CONNECT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CONNECT)


def git(*args):
    return subprocess.run(['git', *map(str,args)], capture_output=True, text=True, check=True).stdout.strip()


class ConnectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root/'remote'
        self.repo.mkdir()
        git('init','--initial-branch=main',self.repo)
        (self.repo/'sample-skill').mkdir()
        (self.repo/'sample-skill/SKILL.md').write_text('Synthetic skill fixture\n')
        (self.repo/'README.md').write_text('Fixture repository\n')
        git('-C',self.repo,'add','.')
        git('-C',self.repo,'-c','user.name=Fixture','-c','user.email=fixture@example.invalid',
            'commit','-m','Fixture baseline')
        self.target = self.root/'installed'

    def test_existing_skills_preserved_and_repeat_is_safe(self):
        skill = self.target/'sample-skill/SKILL.md'
        skill.parent.mkdir(parents=True)
        skill.write_text((self.repo/'sample-skill/SKILL.md').read_text())
        extra = self.target/'extra-local.txt'
        extra.write_text('Preserve untracked local data')
        before = (CONNECT.digest(skill),skill.stat().st_mtime_ns)
        CONNECT.connect(str(self.repo),self.target)
        self.assertEqual((CONNECT.digest(skill),skill.stat().st_mtime_ns),before)
        self.assertEqual(extra.read_text(),'Preserve untracked local data')
        self.assertEqual(Path(git('-C',self.target,'rev-parse','--show-toplevel')),self.target)
        self.assertEqual(git('-C',self.target,'remote','get-url','origin'),str(self.repo))
        CONNECT.connect(str(self.repo),self.target)
        self.assertEqual((CONNECT.digest(skill),skill.stat().st_mtime_ns),before)

    def test_conflicting_skill_stops_before_copying_or_attaching_git(self):
        skill = self.target/'sample-skill/SKILL.md'
        skill.parent.mkdir(parents=True)
        skill.write_text('Local edits')
        with self.assertRaisesRegex(ValueError,'Existing file differs'):
            CONNECT.connect(str(self.repo),self.target)
        self.assertEqual(skill.read_text(),'Local edits')
        self.assertFalse((self.target/'.git').exists())
        self.assertFalse((self.target/'README.md').exists())

    def test_preference_preserves_existing_text_backup_and_override(self):
        home = self.root/'codex-home'
        home.mkdir()
        base = home/'AGENTS.md'
        base.write_text('Keep unrelated instructions.\n')
        CONNECT.preference(self.target,home)
        text = base.read_text()
        self.assertTrue(text.startswith('Keep unrelated instructions.'))
        self.assertIn('Personal skills repository',text)
        self.assertEqual((home/'AGENTS.md.before-codex-skills').read_text(),'Keep unrelated instructions.\n')
        CONNECT.preference(self.target,home)
        self.assertEqual(base.read_text(),text)
        override = home/'AGENTS.override.md'
        override.write_text('Active override.\n')
        CONNECT.preference(self.target,home)
        self.assertEqual(base.read_text(),text)
        self.assertTrue(override.read_text().startswith('Active override.'))
        self.assertIn('Personal skills repository',override.read_text())

    def test_malformed_managed_preference_is_not_overwritten(self):
        home = self.root/'codex-home'
        home.mkdir()
        file = home/'AGENTS.md'
        file.write_text('Unrelated text\n'+CONNECT.START)
        before = file.read_text()
        with self.assertRaisesRegex(ValueError,'Malformed'):
            CONNECT.preference(self.target,home)
        self.assertEqual(file.read_text(),before)


if __name__ == '__main__':
    unittest.main()
