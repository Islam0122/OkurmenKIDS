"""Bulk content import: parsing, validation, duplicates, permissions, import."""
from __future__ import annotations

import datetime as dt
import io
import zipfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from openpyxl import Workbook, load_workbook
from rest_framework.test import APIClient

from apps.academy_news.models import Article
from apps.projects.tests import make_user
from apps.users.models import User

from ..models import Achievement, Branch, Event, ImportBatch, Workflow
from .reader import FileRejected, read_upload
from .schema import normalize_header
from .validate import RowValidator

URL = "/api/v1/marketing/site/import/"

EVENT_HEAD = ["title_ru", "title_kg", "title_en", "category", "starts_at", "ends_at", "location", "status", "cover",
              "verification_note"]
ACH_HEAD = ["Название (RU)", "Название (KG)", "Категория", "Дата", "Получатель", "Статус"]
NEWS_HEAD = ["title_ru", "title_en", "category", "status"]


def xlsx(sheets: dict[str, list[list]], name="content.xlsx") -> SimpleUploadedFile:
    wb = Workbook()
    wb.active.title = "README"
    wb.active.append(["Инструкция"])
    for title, rows in sheets.items():
        ws = wb.create_sheet(title)
        for row in rows:
            ws.append(row)
    buffer = io.BytesIO()
    wb.save(buffer)
    return SimpleUploadedFile(name, buffer.getvalue(),
                              content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


def sample_file():
    return xlsx({
        "Events": [EVENT_HEAD,
                   ["Хакатон Kids", "Kids хакатону", "Kids Hackathon", "hackathon", "2027-03-14 10:00", "2027-03-14 18:00",
                    "Орозбекова 136", "draft", "hackathon.jpg", "Уточнить число команд"],
                   ["День открытых дверей", "", "", "День открытых дверей", "15.04.2027", "", "", "published", "", ""],
                   ["", "", "", "hackathon", "2027-03-14", "", "", "", "", ""],
                   ["Мастер-класс", "", "", "magic", "31.02.2027", "", "", "unknown", "", ""]],
        "Achievements": [ACH_HEAD,
                         ["Победа на олимпиаде", "Олимпиадада жеңиш", "competition", dt.date(2026, 5, 1), "Алия С.", "review"]],
        "News": [NEWS_HEAD, ["Открыт набор", "Enrollment open", "announcements", "draft"]],
    })


class ParsingTests(TestCase):
    def test_reads_every_content_sheet_and_ignores_readme(self):
        sheets = read_upload(sample_file())
        self.assertEqual(set(sheets), {"events", "achievements", "news"})
        self.assertEqual(len(sheets["events"][1]), 4)
        self.assertEqual(sheets["events"][1][0][0], 2)  # spreadsheet row number

    def test_csv_with_semicolon_and_cp1251(self):
        text = "title_ru;category;date\nНаграда;award;2026-01-10\n"
        upload = SimpleUploadedFile("achievements.csv", text.encode("cp1251"), content_type="text/csv")
        sheets = read_upload(upload)
        self.assertEqual(sheets["achievements"][1][0][1]["title_ru"], "Награда")

    def test_csv_needs_a_type(self):
        with self.assertRaises(FileRejected):
            read_upload(SimpleUploadedFile("data.csv", b"title_ru\nX\n"))

    def test_rejects_wrong_extension_fake_xlsx_and_macros(self):
        with self.assertRaises(FileRejected):
            read_upload(SimpleUploadedFile("x.exe", b"MZ..."))
        with self.assertRaises(FileRejected):
            read_upload(SimpleUploadedFile("x.xlsx", b"not a zip at all"))
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as z:
            z.writestr("xl/vbaProject.bin", b"macro")
        with self.assertRaises(FileRejected):
            read_upload(SimpleUploadedFile("x.xlsx", buffer.getvalue()))

    @override_settings()
    def test_rejects_too_large_file(self):
        from . import reader
        upload = SimpleUploadedFile("big.csv", b"a" * (reader.MAX_FILE_BYTES + 1))
        with self.assertRaises(FileRejected):
            read_upload(upload, csv_kind="news")

    def test_header_aliases(self):
        self.assertEqual(normalize_header("Название (RU)*"), "title_ru")
        self.assertEqual(normalize_header("Title KG"), "title_ky")
        self.assertEqual(normalize_header("Обложка"), "cover")
        self.assertEqual(normalize_header("Примечание"), "verification_note")


class ValidationTests(TestCase):
    def validate(self, kind, **cells):
        return RowValidator().validate(kind, 2, cells)

    def test_valid_event_with_translations(self):
        row = self.validate("events", title_ru="Хакатон", title_kg="Хакатон", title_en="Hackathon",
                            category="Хакатон", starts_at="2027-03-14 10:00", cover="a.jpg")
        self.assertTrue(row["valid"], row["errors"])
        self.assertEqual(row["values"]["category"], "hackathon")
        self.assertEqual(row["languages"], {"ru": True, "ky": True, "en": True})
        self.assertEqual(row["warnings"], [])

    def test_blocking_errors(self):
        row = self.validate("events", category="magic", starts_at="31.02.2027", status="whatever")
        fields = {e["field"] for e in row["errors"]}
        self.assertEqual(fields, {"title_ru", "category", "starts_at", "status"})
        self.assertFalse(row["valid"])

    def test_end_before_start_and_unknown_branch(self):
        row = self.validate("events", title_ru="X", category="other", starts_at="2027-01-02 10:00",
                            ends_at="2027-01-01 10:00", branch="Нет такого")
        self.assertEqual({e["field"] for e in row["errors"]}, {"ends_at", "branch"})

    def test_known_branch_is_linked(self):
        branch = Branch.objects.create(name="Орозбекова", address="Орозбекова, 136")
        row = self.validate("events", title_ru="X", category="other", starts_at="2027-01-02 10:00", branch="орозбекова")
        self.assertEqual(row["values"]["branch_id"], branch.pk)

    def test_warnings_do_not_block(self):
        row = self.validate("achievements", title_ru="Награда", category="award", date="2026-01-10", status="published")
        self.assertTrue(row["valid"])
        messages = " ".join(w["message"] for w in row["warnings"])
        self.assertIn("KG", messages)
        self.assertIn("EN", messages)
        self.assertIn("изображения", messages)
        self.assertEqual(row["status"], "draft")  # never published

    def test_news_translations_are_kept_aside(self):
        row = self.validate("news", title_ru="Набор", title_en="Enrollment", category="announcements")
        self.assertTrue(row["valid"])
        self.assertNotIn("title_en", row["values"])
        self.assertEqual(row["translations"]["title_en"], "Enrollment")

    def test_duplicate_rows_in_one_file(self):
        validator = RowValidator()
        first = validator.validate("achievements", 2, {"title_ru": "Награда", "category": "award", "date": "2026-01-10"})
        second = validator.validate("achievements", 3, {"title_ru": " награда ", "category": "award", "date": "10.01.2026"})
        self.assertTrue(first["valid"])
        self.assertFalse(second["valid"])
        self.assertIn("строки 2", second["errors"][0]["message"])

    def test_existing_record_is_a_duplicate_warning(self):
        existing = Achievement.objects.create(title="Награда", category="award", date=dt.date(2026, 1, 10))
        row = self.validate("achievements", title_ru="НАГРАДА", category="award", date="2026-01-10")
        self.assertTrue(row["valid"])
        self.assertEqual(row["duplicate"]["id"], existing.pk)
        self.assertTrue(row["duplicate"]["updatable"])
        other_date = self.validate("achievements", title_ru="Награда", category="award", date="2026-02-10")
        self.assertIsNone(other_date["duplicate"])


class ApiTests(TestCase):
    def setUp(self):
        self.admin = make_user("imp_admin", role=User.Role.ADMIN)
        self.director = make_user("imp_dir", role=User.Role.DIRECTOR)
        self.marketing = make_user("imp_mkt", role=User.Role.MARKETING)
        self.client = APIClient()

    def as_(self, user):
        self.client.force_authenticate(user)
        return self.client

    def preview(self, user=None, upload=None, **data):
        return self.as_(user or self.admin).post(f"{URL}preview/", {"file": upload or sample_file(), **data},
                                                 format="multipart")

    def test_permissions(self):
        self.assertEqual(self.preview(self.marketing).status_code, 403)
        self.assertEqual(self.as_(self.marketing).get(f"{URL}template/").status_code, 403)
        teacher = make_user("imp_teacher", role=User.Role.TEACHER)
        self.assertEqual(self.preview(teacher).status_code, 403)
        self.client.force_authenticate(None)
        self.assertIn(self.client.get(URL).status_code, (401, 403))
        self.assertEqual(self.preview(self.director).status_code, 201)
        with override_settings(WEBSITE_IMPORT_ALLOW_MARKETING=True):
            self.assertEqual(self.preview(self.marketing).status_code, 201)
        meta = self.as_(self.admin).get("/api/v1/marketing/site/meta/").json()
        self.assertTrue(meta["permissions"]["can_import"])

    def test_preview_returns_validated_rows_and_writes_nothing(self):
        r = self.preview()
        self.assertEqual(r.status_code, 201, r.content)
        data = r.json()
        self.assertEqual(data["total_rows"], 6)
        self.assertEqual(data["sheets"], {"events": 4, "achievements": 1, "news": 1})
        self.assertEqual(data["error_rows"], 2)
        self.assertNotIn("values", data["rows"][0])
        self.assertEqual(Event.objects.count() + Achievement.objects.count() + Article.objects.count(), 0)

    def test_selected_sheets_only(self):
        data = self.preview(types="news").json()
        self.assertEqual(data["sheets"], {"news": 1})
        self.assertEqual(data["content_type"], "news")

    def test_bad_file_is_a_400(self):
        r = self.preview(upload=SimpleUploadedFile("x.xlsx", b"garbage"))
        self.assertEqual(r.status_code, 400)
        self.assertIn("file", r.json())

    def test_import_creates_unpublished_records_and_skips_invalid(self):
        batch = self.preview().json()
        keys = [row["key"] for row in batch["rows"]]
        r = self.as_(self.admin).post(f"{URL}{batch['id']}/commit/", {"rows": keys}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        data = r.json()
        self.assertEqual((data["created_count"], data["failed_count"], data["skipped_count"]), (4, 2, 0))
        self.assertEqual(data["status"], "partial")
        hackathon = Event.objects.get(title="Хакатон Kids")
        self.assertEqual(hackathon.status, Workflow.DRAFT)
        self.assertEqual(hackathon.title_ky, "Kids хакатону")
        self.assertEqual(hackathon.created_by, self.admin)
        self.assertEqual(Event.objects.get(title="День открытых дверей").status, Workflow.DRAFT)  # «published» in file
        self.assertEqual(Achievement.objects.get().status, Workflow.REVIEW)  # source status preserved
        self.assertEqual(Achievement.objects.get().recipient, "Алия С.")
        news = Article.objects.get()
        self.assertEqual((news.status, news.author), (Article.Status.DRAFT, self.admin))
        self.assertFalse(Event.objects.public().exists() or Achievement.objects.public().exists()
                         or Article.objects.public().exists())
        # Verification notes kept in the batch report
        result = data["results"][batch["rows"][0]["key"]]
        self.assertEqual(result["verification_note"], "Уточнить число команд")
        # History and the error report
        history = self.as_(self.admin).get(URL).json()
        self.assertEqual(history["results"][0]["id"], batch["id"])
        csv_text = self.as_(self.admin).get(f"{URL}{batch['id']}/errors/").content.decode("utf-8-sig")
        self.assertIn("Неизвестная категория", csv_text)
        # A batch is imported once
        again = self.as_(self.admin).post(f"{URL}{batch['id']}/commit/", {"rows": keys}, format="json")
        self.assertEqual(again.status_code, 400)

    def test_chunked_import_with_progress(self):
        batch = self.preview(types="events").json()
        valid = [r["key"] for r in batch["rows"] if r["valid"]]
        first = self.as_(self.admin).post(f"{URL}{batch['id']}/commit/", {"rows": valid[:1], "finalize": False},
                                          format="json").json()
        self.assertEqual((first["status"], first["created_count"]), ("importing", 1))
        last = self.as_(self.admin).post(f"{URL}{batch['id']}/commit/", {"rows": valid, "finalize": True},
                                         format="json").json()
        self.assertEqual((last["status"], last["created_count"]), ("completed", 2))  # row 1 not imported twice
        self.assertEqual(Event.objects.count(), 2)

    def test_duplicates_skipped_unless_update_confirmed(self):
        existing = Event.objects.create(title="Хакатон Kids", category="hackathon", status=Workflow.DRAFT,
                                        starts_at=timezone.make_aware(dt.datetime(2027, 3, 14, 9, 0)))
        batch = self.preview(types="events").json()
        key = batch["rows"][0]["key"]
        self.assertEqual(batch["rows"][0]["duplicate"]["id"], existing.pk)
        # Skipped by default
        data = self.as_(self.admin).post(f"{URL}{batch['id']}/commit/", {"rows": [key]}, format="json").json()
        self.assertEqual(data["results"][key]["result"], "skipped")
        self.assertEqual(Event.objects.count(), 1)
        # Update requires explicit confirmation
        batch = self.preview(types="events").json()
        r = self.as_(self.admin).post(f"{URL}{batch['id']}/commit/", {"rows": [key], "update": [key]}, format="json")
        self.assertEqual(r.status_code, 400)
        data = self.as_(self.admin).post(f"{URL}{batch['id']}/commit/",
                                         {"rows": [key], "update": [key], "confirm_update": True}, format="json").json()
        self.assertEqual(data["results"][key]["result"], "updated")
        existing.refresh_from_db()
        self.assertEqual((existing.location, existing.title_en, existing.status), ("Орозбекова 136", "Kids Hackathon", "draft"))

    def test_published_record_is_never_updated(self):
        existing = Event.objects.create(title="Хакатон Kids", category="hackathon", status=Workflow.PUBLISHED,
                                        starts_at=timezone.make_aware(dt.datetime(2027, 3, 14, 9, 0)), location="Старое")
        batch = self.preview(types="events").json()
        key = batch["rows"][0]["key"]
        data = self.as_(self.admin).post(f"{URL}{batch['id']}/commit/",
                                         {"rows": [key], "update": [key], "confirm_update": True}, format="json").json()
        self.assertEqual(data["results"][key]["result"], "skipped")
        existing.refresh_from_db()
        self.assertEqual(existing.location, "Старое")

    def test_cannot_import_other_rows_or_cancelled_batch(self):
        batch = self.preview().json()
        r = self.as_(self.admin).post(f"{URL}{batch['id']}/commit/", {"rows": ["events:999"]}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.as_(self.admin).post(f"{URL}{batch['id']}/cancel/").status_code, 200)
        r = self.as_(self.admin).post(f"{URL}{batch['id']}/commit/", {"rows": [batch["rows"][0]["key"]]}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(ImportBatch.objects.get().status, "cancelled")

    def test_templates(self):
        r = self.as_(self.admin).get(f"{URL}template/?file_format=xlsx")
        self.assertEqual(r.status_code, 200)
        wb = load_workbook(io.BytesIO(r.content))
        self.assertEqual(wb.sheetnames, ["README", "Events", "Achievements", "News"])
        self.assertEqual(wb["Events"].max_row, 1)  # headers only, no sample records
        # The template itself round-trips through the reader
        upload = SimpleUploadedFile("t.xlsx", r.content)
        self.assertEqual({k: len(v[1]) for k, v in read_upload(upload).items()},
                         {"events": 0, "achievements": 0, "news": 0})
        csv_r = self.as_(self.admin).get(f"{URL}template/?file_format=csv&type=news")
        self.assertTrue(csv_r.content.decode("utf-8-sig").startswith("title_ru,title_ky"))
        self.assertEqual(self.as_(self.admin).get(f"{URL}template/?file_format=csv").status_code, 400)
