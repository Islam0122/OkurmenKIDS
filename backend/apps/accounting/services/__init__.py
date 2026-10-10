"""Сервисный слой бухгалтерии: расчёт (payroll_calculator), утверждение и
корректировки (approval_service), выплаты (payment_service), платежи
студентов (student_payments), отчёты (report_service / report_pdf /
report_xlsx). Представления и сериализаторы только вызывают эти функции."""


class AccountingError(Exception):
    """Нарушение бизнес-правила бухгалтерии — показывается пользователю как 400."""

    def __init__(self, message: str, *, code: str = "invalid"):
        super().__init__(message)
        self.message = message
        self.code = code
