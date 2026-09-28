"""Step 2 of 2: the money rules as database constraints (data was checked
in 0006), and no CASCADE from a student / user to financial history."""
from decimal import Decimal

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("academy", "0017_student_enrollment_date"),
        ("scholarships", "0006_award_money_integrity_data"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="scholarshipaward",
            name="scholarship_award_paid_is_approved",
        ),
        migrations.AlterField(
            model_name="scholarshipaward",
            name="amount",
            field=models.DecimalField(
                decimal_places=2, max_digits=10,
                validators=[django.core.validators.MinValueValidator(Decimal("0"))], verbose_name="Сумма",
            ),
        ),
        migrations.AlterField(
            model_name="scholarshipaward",
            name="evaluation",
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.RESTRICT, related_name="award",
                to="scholarships.scholarshipevaluation", verbose_name="Оценка",
            ),
        ),
        migrations.AlterField(
            model_name="scholarshipaward",
            name="paid_by",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="+",
                to=settings.AUTH_USER_MODEL, verbose_name="Выдал",
            ),
        ),
        migrations.AlterField(
            model_name="scholarshipaward",
            name="student",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.RESTRICT, related_name="scholarship_awards",
                to="academy.student", verbose_name="Студент",
            ),
        ),
        migrations.AddConstraint(
            model_name="scholarshipaward",
            constraint=models.CheckConstraint(
                condition=models.Q(("amount__gte", 0)), name="scholarship_award_amount_non_negative",
            ),
        ),
        migrations.AddConstraint(
            model_name="scholarshipaward",
            constraint=models.CheckConstraint(
                condition=models.Q(("payment_status__in", ["unpaid", "paid"])),
                name="scholarship_award_payment_status_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="scholarshipaward",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("payment_status", "paid"), _negated=True),
                    models.Q(
                        ("amount__gt", 0), ("paid_amount__gte", 0), ("paid_amount__isnull", False),
                        ("paid_amount__lte", models.F("amount")), ("paid_at__isnull", False),
                        ("paid_by__isnull", False), ("status", "approved"),
                        models.Q(("payment_method", ""), _negated=True),
                        models.Q(("paid_by_name", ""), _negated=True),
                    ),
                    _connector="OR",
                ),
                name="scholarship_award_paid_is_complete",
            ),
        ),
        migrations.AddConstraint(
            model_name="scholarshipaward",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(("payment_status", "unpaid"), _negated=True),
                    models.Q(
                        ("paid_amount__isnull", True), ("paid_at__isnull", True), ("paid_by__isnull", True),
                        ("paid_by_name", ""), ("payment_method", ""),
                    ),
                    _connector="OR",
                ),
                name="scholarship_award_unpaid_is_blank",
            ),
        ),
    ]
