import json, subprocess, sys, re
S = sys.argv[1]; voice = sys.argv[2]; rate = sys.argv[3]
scenes = json.load(open(S + "/vo/script.json"))
rep = [("Okurmen Kids LMS", "Окурмэн Кидс эл-эм-эс"), ("Okurmen Kids", "Окурмэн Кидс"), ("EdTech", "эд-тех"),
       ("Django REST Framework", "Джанго рэст фрэймворк"), ("Django", "Джанго"), ("PostgreSQL", "Постгрэс-кью-эль"), ("Python", "Пайтон"),
       ("Celery", "Сэлери"), ("Redis", "Рэдис"), ("React", "Риэкт"), ("TypeScript", "ТайпСкрипт"), ("PWA", "пи-дабл-ю-эй"),
       ("push-уведомлениями", "пуш-уведомлениями"), ("Backend", "Бэкенд"), ("Docker", "Докере"), ("Railway", "Рэйлвэй"), ("Vercel", "Вёрсел"),
       ("QR-код", "кью-ар код"), ("KPI", "кей-пи-ай"), ("PDF", "пи-ди-эф"), ("Excel", "эксэль"), ("HR", "эйч-ар")]
out = {}
for sc in scenes:
    t = sc["text"]
    for a, b in rep: t = t.replace(a, b)
    t = t.replace("—", ",")
    wav = f"{S}/vo/{sc['id']}.wav"
    subprocess.run(["RHVoice-test", "-p", voice, "-r", rate, "-o", wav], input=t.encode(), check=True)
    d = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", wav]))
    out[sc["id"]] = round(d, 2); print(sc["id"], round(d, 2))
print("total", round(sum(out.values()), 1)); json.dump(out, open(S + "/vo/durations.json", "w"))
