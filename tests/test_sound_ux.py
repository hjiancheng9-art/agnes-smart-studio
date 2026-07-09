"""Tests for core/sound_ux.py"""

from core.sound_ux import SoundUX


class TestSoundUX:
    def test_create(self):
        sux = SoundUX()
        assert sux is not None

    def test_startup_sound(self):
        sux = SoundUX()
        sux.startup()

    def test_alert(self):
        sux = SoundUX()
        sux.alert()

    def test_success(self):
        sux = SoundUX()
        sux.success()

    def test_error_sound(self):
        sux = SoundUX()
        sux.error()

    def test_toggle(self):
        sux = SoundUX()
        sux.toggle()

    def test_alchemy(self):
        sux = SoundUX()
        sux.alchemy()
