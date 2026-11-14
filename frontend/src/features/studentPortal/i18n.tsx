import { createContext, useCallback, useContext, useMemo, useState } from 'react'
import type { ReactNode } from 'react'

/**
 * Russian / Kyrgyz for the Student & Parent Portal. The backend sends codes
 * and parameters (statuses, notification kinds, achievements), never ready
 * text — every word the family reads is here. The chosen language is a
 * per-device convenience (localStorage); nothing depends on it server-side
 * except the PDF, which is requested in the same language.
 */

export type Lang = 'ru' | 'ky'
const STORAGE_KEY = 'okk-student-portal-lang'

const ru = {
  'brand.portal': 'Кабинет ученика',
  'nav.home': 'Главная',
  'nav.schedule': 'Расписание',
  'nav.homework': 'Задания',
  'nav.attendance': 'Посещаемость',
  'nav.reports': 'Отчёты',
  'nav.payments': 'Оплата',
  'nav.profile': 'Профиль',
  'nav.logout': 'Выйти',
  'switcher.label': 'Ребёнок',
  'common.loading': 'Загружаем…',
  'common.error': 'Не удалось загрузить данные.',
  'common.retry': 'Повторить',
  'common.noData': 'Нет данных',
  'common.all': 'Все',
  'common.today': 'Сегодня',
  'common.tomorrow': 'Завтра',
  'common.back': 'Назад',
  'common.save': 'Сохранить',
  'common.of': 'из',
  'common.lessonsCount': '{n} занятий',
  'common.som': 'сом',
  'common.table': 'Таблица',
  'common.chart': 'График',

  'dash.hello': 'Здравствуйте!',
  'dash.subtitle': '{group} · {course}',
  'dash.today': 'Сегодня',
  'dash.noLessonsToday': 'Сегодня занятий нет.',
  'dash.upcoming': 'Ближайшие занятия',
  'dash.noUpcoming': 'Ближайших занятий нет.',
  'dash.homework': 'Домашние задания',
  'dash.openCount': 'Открыто: {n}',
  'dash.overdueCount': 'просрочено: {n}',
  'dash.noOpenHomework': 'Все задания сданы — отлично!',
  'dash.attendance': 'Посещаемость',
  'dash.thisMonth': 'в этом месяце',
  'dash.overall': 'за всё время',
  'dash.performance': 'Успеваемость',
  'dash.avgScore': 'Средний балл',
  'dash.hwRate': 'Задания выполнены',
  'dash.xp': 'Опыт',
  'dash.level': 'Уровень {n}',
  'dash.xpToNext': 'до следующего уровня: {n} XP',
  'dash.xpMonth': '+{n} XP в этом месяце',
  'dash.achievements': 'Достижения',
  'dash.noAchievements': 'Первые достижения появятся после занятий и заданий.',
  'dash.feedback': 'Отзывы тренеров',
  'dash.noFeedback': 'Пока отзывов нет.',
  'dash.notifications': 'Уведомления',
  'dash.noNotifications': 'Новых уведомлений нет.',
  'dash.payments': 'Оплата',
  'dash.debt': 'К оплате',
  'dash.paid': 'Оплачено',
  'dash.allPaid': 'Задолженности нет',
  'dash.details': 'Подробнее',

  'lesson.status.scheduled': 'Запланировано',
  'lesson.status.in_progress': 'Идёт сейчас',
  'lesson.status.completed': 'Проведено',
  'lesson.status.cancelled': 'Отменено',
  'lesson.room': 'Каб. {room}',
  'lesson.number': 'Урок {n}',
  'att.present': 'Был',
  'att.late': 'Опоздал',
  'att.absent': 'Пропустил',
  'att.excused': 'Уваж. причина',

  'schedule.title': 'Расписание',
  'schedule.week': 'Неделя',
  'schedule.month': 'Месяц',
  'schedule.prev': 'Назад',
  'schedule.next': 'Вперёд',
  'schedule.current': 'Сегодня',
  'schedule.empty': 'В этот период занятий нет.',
  'schedule.subject': 'Предмет',
  'schedule.teacher': 'Тренер',
  'schedule.group': 'Группа',
  'schedule.branch': 'Филиал',
  'schedule.time': 'Время',

  'hw.title': 'Домашние задания',
  'hw.filter.open': 'Открытые',
  'hw.filter.done': 'Сданные',
  'hw.filter.overdue': 'Просроченные',
  'hw.filter.checked': 'Проверенные',
  'hw.state.pending': 'Нужно сдать',
  'hw.state.overdue': 'Просрочено',
  'hw.state.submitted': 'Сдано',
  'hw.state.late': 'Сдано с опозданием',
  'hw.state.checked': 'Проверено',
  'hw.deadline': 'Срок: {date}',
  'hw.noDeadline': 'Без срока',
  'hw.daysLeft': 'осталось дней: {n}',
  'hw.dueToday': 'сдать сегодня',
  'hw.empty': 'Заданий нет.',
  'hw.lesson': 'Занятие {date}',
  'hw.description': 'Задание',
  'hw.noDescription': 'Описание не добавлено — уточните у тренера.',
  'hw.attachments': 'Материалы занятия',
  'hw.video': 'Видео',
  'hw.presentation': 'Презентация',
  'hw.feedback': 'Отзыв тренера',
  'hw.score': 'Оценка: {score} / 10',
  'hw.yourWork': 'Ваша работа',
  'hw.answer': 'Ответ',
  'hw.answerPlaceholder': 'Напишите ответ или комментарий к работе',
  'hw.link': 'Ссылка на работу',
  'hw.linkPlaceholder': 'https://github.com/… или ссылка на Google Диск',
  'hw.submit': 'Сдать работу',
  'hw.resubmit': 'Отправить заново',
  'hw.submitted': 'Работа отправлена тренеру',
  'hw.locked': 'Работа проверена — изменить её нельзя.',
  'hw.lateWarning': 'Срок прошёл — работа будет отмечена как сданная с опозданием.',

  'attendance.title': 'Посещаемость',
  'attendance.percent': 'Посещаемость',
  'attendance.attended': 'Был на занятиях',
  'attendance.missed': 'Пропуски',
  'attendance.late': 'Опоздания',
  'attendance.excused': 'По уважительной',
  'attendance.empty': 'В этом месяце отметок нет.',

  'report.title': 'Отчёты для родителей',
  'report.subtitle': 'Ежемесячный отчёт по реальным данным: посещаемость, задания, тесты и отзывы.',
  'report.preliminary': 'Месяц ещё идёт — отчёт предварительный.',
  'report.download': 'Скачать PDF',
  'report.attendance': 'Посещаемость',
  'report.totalLessons': 'Проведено занятий',
  'report.attended': 'Посетил',
  'report.missed': 'Пропустил',
  'report.homework': 'Домашние задания',
  'report.completion': 'Выполнено',
  'report.avgScore': 'Средний балл',
  'report.tests': 'Тесты',
  'report.testsAvg': 'Средний результат',
  'report.noTests': 'В этом месяце тестов не было.',
  'report.xp': 'Опыт за месяц',
  'report.xpAttendance': 'за посещение',
  'report.xpHomework': 'за задания',
  'report.xpTests': 'за тесты',
  'report.progress': 'Успеваемость по предметам',
  'report.trend': 'Динамика за полгода',
  'report.trendXp': 'Опыт по месяцам',
  'report.comments': 'Комментарии тренеров',
  'report.noComments': 'Комментариев за этот месяц нет.',
  'report.change': '{sign}{n} к прошлому месяцу',
  'report.subject': 'Предмет',
  'report.lessons': 'Занятия',
  'report.month': 'Месяц',

  'pay.title': 'Оплата обучения',
  'pay.noContracts': 'Договоров оплаты пока нет.',
  'pay.price': 'Стоимость курса',
  'pay.invoiced': 'Начислено',
  'pay.paid': 'Оплачено',
  'pay.debt': 'Задолженность',
  'pay.dueNow': 'К оплате сейчас',
  'pay.overpayment': 'Переплата',
  'pay.open': 'Ожидают оплаты',
  'pay.history': 'История платежей',
  'pay.noHistory': 'Платежей пока нет.',
  'pay.refund': 'Возврат',
  'pay.payment': 'Оплата',
  'pay.balance': 'Остаток: {n}',
  'pay.hidden': 'Информация об оплате скрыта для этого кабинета.',

  'pwd.title': 'Придумайте свой пароль',
  'pwd.subtitle': 'Вы вошли с временным паролем. Чтобы открыть кабинет, задайте собственный пароль.',
  'pwd.changeTitle': 'Смена пароля',
  'pwd.current': 'Текущий (временный) пароль',
  'pwd.new': 'Новый пароль',
  'pwd.confirm': 'Повторите новый пароль',
  'pwd.hint': 'Не короче 8 символов, не только цифры и не похожий на логин.',
  'pwd.mismatch': 'Пароли не совпадают.',
  'pwd.submit': 'Сохранить пароль',
  'pwd.done': 'Пароль изменён',

  'profile.title': 'Профиль',
  'profile.login': 'Логин',
  'profile.children': 'Дети в кабинете',
  'profile.language': 'Язык',
  'profile.branch': 'Филиал',
  'profile.birth': 'Дата рождения',
  'profile.start': 'Учится с',

  'notif.homework_overdue': 'Просрочено задание «{title}»',
  'notif.homework_due': 'Скоро срок: «{title}»',
  'notif.homework_due_today': 'Сегодня срок сдачи: «{title}»',
  'notif.homework_new': 'Новое задание: «{title}»',
  'notif.homework_checked': 'Задание «{title}» проверено',
  'notif.homework_checked_score': 'Задание «{title}» проверено — {score}/10',
  'notif.lesson_cancelled': 'Занятие {subject} отменено',
  'notif.payment_due': 'Ожидается оплата: {amount} сом',

  'ach.scholarship': 'Стипендия · {rank} место',
  'ach.perfect_attendance': 'Без пропусков · {month}',
  'ach.top_homework': '{count}+ заданий на 10 баллов',
  'ach.homework_streak': '{count}+ сданных заданий',
  'ach.level': 'Уровень {level}',

  'feedback.homework': 'Задание',
  'feedback.lesson': 'Занятие',
  'feedback.evaluation': 'Оценка тренера',
}

type Key = keyof typeof ru

const ky: Record<Key, string> = {
  'brand.portal': 'Окуучунун кабинети',
  'nav.home': 'Башкы бет',
  'nav.schedule': 'Сабак тартиби',
  'nav.homework': 'Тапшырмалар',
  'nav.attendance': 'Катышуу',
  'nav.reports': 'Отчёттор',
  'nav.payments': 'Төлөм',
  'nav.profile': 'Профиль',
  'nav.logout': 'Чыгуу',
  'switcher.label': 'Бала',
  'common.loading': 'Жүктөлүүдө…',
  'common.error': 'Маалыматты жүктөө мүмкүн болбоду.',
  'common.retry': 'Кайталоо',
  'common.noData': 'Маалымат жок',
  'common.all': 'Баары',
  'common.today': 'Бүгүн',
  'common.tomorrow': 'Эртең',
  'common.back': 'Артка',
  'common.save': 'Сактоо',
  'common.of': '/',
  'common.lessonsCount': '{n} сабак',
  'common.som': 'сом',
  'common.table': 'Таблица',
  'common.chart': 'График',

  'dash.hello': 'Саламатсызбы!',
  'dash.subtitle': '{group} · {course}',
  'dash.today': 'Бүгүн',
  'dash.noLessonsToday': 'Бүгүн сабак жок.',
  'dash.upcoming': 'Жакынкы сабактар',
  'dash.noUpcoming': 'Жакынкы сабактар жок.',
  'dash.homework': 'Үй тапшырмалары',
  'dash.openCount': 'Ачык: {n}',
  'dash.overdueCount': 'мөөнөтү өткөн: {n}',
  'dash.noOpenHomework': 'Бардык тапшырмалар өткөрүлдү — азаматсың!',
  'dash.attendance': 'Катышуу',
  'dash.thisMonth': 'бул айда',
  'dash.overall': 'бардык убакытта',
  'dash.performance': 'Жетишкендик',
  'dash.avgScore': 'Орточо балл',
  'dash.hwRate': 'Аткарылган тапшырмалар',
  'dash.xp': 'Тажрыйба',
  'dash.level': '{n}-деңгээл',
  'dash.xpToNext': 'кийинки деңгээлге чейин: {n} XP',
  'dash.xpMonth': 'бул айда +{n} XP',
  'dash.achievements': 'Жетишкендиктер',
  'dash.noAchievements': 'Алгачкы жетишкендиктер сабактардан жана тапшырмалардан кийин пайда болот.',
  'dash.feedback': 'Машыктыруучулардын пикири',
  'dash.noFeedback': 'Азырынча пикир жок.',
  'dash.notifications': 'Билдирүүлөр',
  'dash.noNotifications': 'Жаңы билдирүү жок.',
  'dash.payments': 'Төлөм',
  'dash.debt': 'Төлөөгө',
  'dash.paid': 'Төлөндү',
  'dash.allPaid': 'Карыз жок',
  'dash.details': 'Толугураак',

  'lesson.status.scheduled': 'Пландалган',
  'lesson.status.in_progress': 'Азыр жүрүп жатат',
  'lesson.status.completed': 'Өттү',
  'lesson.status.cancelled': 'Жокко чыгарылды',
  'lesson.room': '{room}-каб.',
  'lesson.number': '{n}-сабак',
  'att.present': 'Келди',
  'att.late': 'Кечикти',
  'att.absent': 'Келген жок',
  'att.excused': 'Жүйөлүү себеп',

  'schedule.title': 'Сабак тартиби',
  'schedule.week': 'Апта',
  'schedule.month': 'Ай',
  'schedule.prev': 'Мурунку',
  'schedule.next': 'Кийинки',
  'schedule.current': 'Бүгүн',
  'schedule.empty': 'Бул мезгилде сабак жок.',
  'schedule.subject': 'Сабак',
  'schedule.teacher': 'Машыктыруучу',
  'schedule.group': 'Топ',
  'schedule.branch': 'Филиал',
  'schedule.time': 'Убакыт',

  'hw.title': 'Үй тапшырмалары',
  'hw.filter.open': 'Ачык',
  'hw.filter.done': 'Өткөрүлгөн',
  'hw.filter.overdue': 'Мөөнөтү өткөн',
  'hw.filter.checked': 'Текшерилген',
  'hw.state.pending': 'Өткөрүү керек',
  'hw.state.overdue': 'Мөөнөтү өттү',
  'hw.state.submitted': 'Өткөрүлдү',
  'hw.state.late': 'Кечигип өткөрүлдү',
  'hw.state.checked': 'Текшерилди',
  'hw.deadline': 'Мөөнөтү: {date}',
  'hw.noDeadline': 'Мөөнөтсүз',
  'hw.daysLeft': '{n} күн калды',
  'hw.dueToday': 'бүгүн өткөрүү керек',
  'hw.empty': 'Тапшырма жок.',
  'hw.lesson': '{date} сабагы',
  'hw.description': 'Тапшырма',
  'hw.noDescription': 'Сүрөттөмө кошулган эмес — машыктыруучудан тактаңыз.',
  'hw.attachments': 'Сабактын материалдары',
  'hw.video': 'Видео',
  'hw.presentation': 'Презентация',
  'hw.feedback': 'Машыктыруучунун пикири',
  'hw.score': 'Баа: {score} / 10',
  'hw.yourWork': 'Сиздин ишиңиз',
  'hw.answer': 'Жооп',
  'hw.answerPlaceholder': 'Жообуңузду же ишке комментарий жазыңыз',
  'hw.link': 'Иштин шилтемеси',
  'hw.linkPlaceholder': 'https://github.com/… же Google Диск шилтемеси',
  'hw.submit': 'Ишти өткөрүү',
  'hw.resubmit': 'Кайра жөнөтүү',
  'hw.submitted': 'Иш машыктыруучуга жөнөтүлдү',
  'hw.locked': 'Иш текшерилди — аны өзгөртүүгө болбойт.',
  'hw.lateWarning': 'Мөөнөтү өттү — иш кечигип өткөрүлгөн деп белгиленет.',

  'attendance.title': 'Катышуу',
  'attendance.percent': 'Катышуу',
  'attendance.attended': 'Сабакка келди',
  'attendance.missed': 'Калтырылган',
  'attendance.late': 'Кечигүүлөр',
  'attendance.excused': 'Жүйөлүү себеп менен',
  'attendance.empty': 'Бул айда белги жок.',

  'report.title': 'Ата-энелер үчүн отчёттор',
  'report.subtitle': 'Чыныгы маалыматтар боюнча айлык отчёт: катышуу, тапшырмалар, тесттер жана пикирлер.',
  'report.preliminary': 'Ай али бүтө элек — отчёт алдын ала.',
  'report.download': 'PDF жүктөө',
  'report.attendance': 'Катышуу',
  'report.totalLessons': 'Өткөн сабактар',
  'report.attended': 'Катышты',
  'report.missed': 'Калтырды',
  'report.homework': 'Үй тапшырмалары',
  'report.completion': 'Аткарылды',
  'report.avgScore': 'Орточо балл',
  'report.tests': 'Тесттер',
  'report.testsAvg': 'Орточо жыйынтык',
  'report.noTests': 'Бул айда тест болгон жок.',
  'report.xp': 'Айдагы тажрыйба',
  'report.xpAttendance': 'катышуу үчүн',
  'report.xpHomework': 'тапшырмалар үчүн',
  'report.xpTests': 'тесттер үчүн',
  'report.progress': 'Сабактар боюнча жетишкендик',
  'report.trend': 'Акыркы алты ай',
  'report.trendXp': 'Айлар боюнча тажрыйба',
  'report.comments': 'Машыктыруучулардын комментарийлери',
  'report.noComments': 'Бул айда комментарий жок.',
  'report.change': 'өткөн айга карата {sign}{n}',
  'report.subject': 'Сабак',
  'report.lessons': 'Сабактар',
  'report.month': 'Ай',

  'pay.title': 'Окуу акысы',
  'pay.noContracts': 'Төлөм келишимдери азырынча жок.',
  'pay.price': 'Курстун баасы',
  'pay.invoiced': 'Эсептелди',
  'pay.paid': 'Төлөндү',
  'pay.debt': 'Карыз',
  'pay.dueNow': 'Азыр төлөөгө',
  'pay.overpayment': 'Ашыкча төлөм',
  'pay.open': 'Төлөм күтүүдө',
  'pay.history': 'Төлөмдөр тарыхы',
  'pay.noHistory': 'Азырынча төлөм жок.',
  'pay.refund': 'Кайтарым',
  'pay.payment': 'Төлөм',
  'pay.balance': 'Калдык: {n}',
  'pay.hidden': 'Бул кабинет үчүн төлөм маалыматы жашырылган.',

  'pwd.title': 'Өз сырсөзүңүздү ойлоп табыңыз',
  'pwd.subtitle': 'Сиз убактылуу сырсөз менен кирдиңиз. Кабинетти ачуу үчүн өз сырсөзүңүздү коюңуз.',
  'pwd.changeTitle': 'Сырсөздү өзгөртүү',
  'pwd.current': 'Учурдагы (убактылуу) сырсөз',
  'pwd.new': 'Жаңы сырсөз',
  'pwd.confirm': 'Жаңы сырсөздү кайталаңыз',
  'pwd.hint': 'Кеминде 8 белги, сандардан гана эмес жана логинге окшош эмес.',
  'pwd.mismatch': 'Сырсөздөр дал келбейт.',
  'pwd.submit': 'Сырсөздү сактоо',
  'pwd.done': 'Сырсөз өзгөртүлдү',

  'profile.title': 'Профиль',
  'profile.login': 'Логин',
  'profile.children': 'Кабинеттеги балдар',
  'profile.language': 'Тил',
  'profile.branch': 'Филиал',
  'profile.birth': 'Туулган күнү',
  'profile.start': 'Окуунун башталышы',

  'notif.homework_overdue': '«{title}» тапшырмасынын мөөнөтү өттү',
  'notif.homework_due': 'Мөөнөтү жакындады: «{title}»',
  'notif.homework_due_today': 'Бүгүн өткөрүү керек: «{title}»',
  'notif.homework_new': 'Жаңы тапшырма: «{title}»',
  'notif.homework_checked': '«{title}» тапшырмасы текшерилди',
  'notif.homework_checked_score': '«{title}» тапшырмасы текшерилди — {score}/10',
  'notif.lesson_cancelled': '{subject} сабагы жокко чыгарылды',
  'notif.payment_due': 'Төлөм күтүлүүдө: {amount} сом',

  'ach.scholarship': 'Стипендия · {rank}-орун',
  'ach.perfect_attendance': 'Калтырбай катышты · {month}',
  'ach.top_homework': '10 баллга {count}+ тапшырма',
  'ach.homework_streak': '{count}+ өткөрүлгөн тапшырма',
  'ach.level': '{level}-деңгээл',

  'feedback.homework': 'Тапшырма',
  'feedback.lesson': 'Сабак',
  'feedback.evaluation': 'Машыктыруучунун баасы',
}

export const DICTIONARIES: Record<Lang, Record<Key, string>> = { ru, ky }

const MONTHS: Record<Lang, string[]> = {
  ru: ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'],
  ky: ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'],
}
const WEEKDAYS: Record<Lang, string[]> = {
  ru: ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'],
  ky: ['Дш', 'Шш', 'Шр', 'Бш', 'Жм', 'Иш', 'Жк'],
}
const WEEKDAYS_FULL: Record<Lang, string[]> = {
  ru: ['Понедельник', 'Вторник', 'Среда', 'Четверг', 'Пятница', 'Суббота', 'Воскресенье'],
  ky: ['Дүйшөмбү', 'Шейшемби', 'Шаршемби', 'Бейшемби', 'Жума', 'Ишемби', 'Жекшемби'],
}

export type TFunction = (key: Key, params?: Record<string, string | number | null | undefined>) => string

interface I18nValue {
  lang: Lang
  setLang: (lang: Lang) => void
  t: TFunction
  month: (index1: number) => string
  weekday: (mondayIndex: number, full?: boolean) => string
  /** dd.MM or «5 ноября»-like short date, locale-neutral. */
  date: (iso: string | null | undefined, withYear?: boolean) => string
}

const I18nContext = createContext<I18nValue | null>(null)

function readLang(): Lang {
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY)
    return stored === 'ky' ? 'ky' : 'ru'
  } catch {
    return 'ru'
  }
}

export function translate(lang: Lang, key: Key, params?: Record<string, string | number | null | undefined>) {
  let text = DICTIONARIES[lang][key] ?? DICTIONARIES.ru[key] ?? key
  if (params) {
    for (const [name, value] of Object.entries(params)) text = text.replaceAll(`{${name}}`, value === null || value === undefined ? '' : String(value))
  }
  return text
}

export function PortalI18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(readLang)
  const setLang = useCallback((next: Lang) => {
    setLangState(next)
    try {
      window.localStorage.setItem(STORAGE_KEY, next)
    } catch {
      /* private mode — the choice just isn't remembered */
    }
  }, [])
  const value = useMemo<I18nValue>(() => ({
    lang,
    setLang,
    t: (key, params) => translate(lang, key, params),
    month: (index1) => MONTHS[lang][index1 - 1] ?? '',
    weekday: (index, full = false) => (full ? WEEKDAYS_FULL : WEEKDAYS)[lang][index] ?? '',
    date: (iso, withYear = false) => {
      if (!iso) return '—'
      const [y, m, d] = iso.slice(0, 10).split('-')
      return withYear ? `${d}.${m}.${y}` : `${d}.${m}`
    },
  }), [lang, setLang])
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>
}

export function usePortalI18n(): I18nValue {
  const value = useContext(I18nContext)
  if (!value) throw new Error('usePortalI18n must be used inside PortalI18nProvider')
  return value
}
