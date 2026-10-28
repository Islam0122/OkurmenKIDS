"""Миграции users.0007 / staff_attendance.0004: роль РОМ упразднена —
её пользователи становятся маркетингом без потери аккаунтов, а из настроек
учёта роль убирается, не трогая остальные."""
from __future__ import annotations

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class RemoveRomRoleMigrationTests(TransactionTestCase):
    before = [("users", "0006_staff_only_roles"), ("staff_attendance", "0003_track_staff_only_roles")]
    after = [("users", "0007_remove_rom_role"), ("staff_attendance", "0004_remove_rom_role")]

    def setUp(self):
        executor = MigrationExecutor(connection)
        executor.migrate(self.before)
        old = executor.loader.project_state(self.before).apps
        User = old.get_model("users", "User")
        Settings = old.get_model("staff_attendance", "AttendanceSettings")
        self.rom = User.objects.create(username="rom_m", email="rom_m@okurmen.kg", role="rom", first_name="Р",
                                       is_active=False)
        self.rop = User.objects.create(username="rop_m", email="rop_m@okurmen.kg", role="rop", first_name="П")
        Settings.objects.all().delete()
        self.tracked = Settings.objects.create(tracked_roles=["teacher", "rom"])
        self.untracked = Settings.objects.create(tracked_roles=["teacher", "rop"])
        executor.loader.build_graph()
        executor.migrate(self.after)
        self.apps = executor.loader.project_state(self.after).apps

    def tearDown(self):
        MigrationExecutor(connection).migrate(MigrationExecutor(connection).loader.graph.leaf_nodes())

    def test_rom_users_become_marketing_and_keep_account(self):
        User = self.apps.get_model("users", "User")
        rom = User.objects.get(pk=self.rom.pk)
        self.assertEqual((rom.role, rom.username, rom.is_active), ("marketing", "rom_m", False))
        self.assertEqual(User.objects.get(pk=self.rop.pk).role, "rop")
        self.assertFalse(User.objects.filter(role="rom").exists())

    def test_rom_removed_from_tracked_roles(self):
        Settings = self.apps.get_model("staff_attendance", "AttendanceSettings")
        self.assertEqual(Settings.objects.get(pk=self.tracked.pk).tracked_roles, ["teacher", "marketing"])
        self.assertEqual(Settings.objects.get(pk=self.untracked.pk).tracked_roles, ["teacher", "rop"])
