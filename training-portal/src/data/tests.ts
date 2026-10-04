import type { Question, Test } from '@/types'

/*
 * Training tests. Static for now — services/contentService.ts is the only
 * reader, so moving these to the Django API later changes nothing in the UI.
 * Option ids are local to a question («a», «b», …).
 */

const opts = (...texts: string[]) => texts.map((text, i) => ({ id: String.fromCharCode(97 + i), text }))

const pythonQuestions: Question[] = [
  {
    id: 'py-01', type: 'single',
    question: 'Python тилинде экранга текст чыгаруу үчүн кайсы функция колдонулат?',
    options: opts('print()', 'echo()', 'console.log()', 'write()'),
    correctAnswer: 'a',
    explanation: 'print() функциясы берилген маанини экранга чыгарат.',
  },
  {
    id: 'py-02', type: 'single',
    question: 'Төмөнкүлөрдүн кайсынысы туура өзгөрмө аты?',
    options: opts('2name', 'my_name', 'my-name', 'class'),
    correctAnswer: 'b',
    explanation: 'Өзгөрмөнүн аты сан менен башталбайт, ичинде дефис (-) болбойт, ал эми class — Python’дун ачкыч сөзү.',
  },
  {
    id: 'py-03', type: 'single',
    question: 'type(3.14) эмнени кайтарат?',
    options: opts("<class 'int'>", "<class 'float'>", "<class 'str'>", "<class 'decimal'>"),
    correctAnswer: 'b',
    explanation: 'Бөлчөк бөлүгү бар сандар float түрүнө кирет.',
  },
  {
    id: 'py-04', type: 'single',
    question: 'len("Python") эмнеге барабар?',
    options: opts('5', '6', '7', 'Ката чыгат'),
    correctAnswer: 'b',
    explanation: 'len() саптагы белгилердин санын кайтарат: P-y-t-h-o-n — 6 белги.',
  },
  {
    id: 'py-05', type: 'multiple',
    question: 'Кайсы маалымат түрлөрү түзүлгөндөн кийин өзгөрбөйт (immutable)?',
    options: opts('tuple', 'str', 'list', 'dict'),
    correctAnswer: ['a', 'b'],
    explanation: 'tuple жана str өзгөрбөйт. list жана dict — өзгөрүүчү (mutable) түрлөр.',
  },
  {
    id: 'py-06', type: 'single',
    question: '10 // 3 туюнтмасынын жыйынтыгы кандай?',
    options: opts('3.33', '3', '1', '4'),
    correctAnswer: 'b',
    explanation: '// — бүтүн бөлүү: жыйынтыктын бөлчөк бөлүгү ташталат.',
  },
  {
    id: 'py-07', type: 'single',
    question: '10 % 3 эмнеге барабар?',
    options: opts('1', '3', '0', '3.3'),
    correctAnswer: 'a',
    explanation: '% — бөлүүдөн калган калдык: 10 = 3 · 3 + 1.',
  },
  {
    id: 'py-08', type: 'text',
    question: 'Тизменин (list) аягына элемент кошуучу методдун атын жазыңыз (кашаасыз).',
    correctAnswer: ['append'],
    explanation: 'list.append(x) тизменин аягына x элементин кошот.',
  },
  {
    id: 'py-09', type: 'single',
    question: 'Python’до функция кайсы ачкыч сөз менен аныкталат?',
    options: opts('func', 'def', 'function', 'fn'),
    correctAnswer: 'b',
    explanation: 'Функция def ачкыч сөзү менен түзүлөт: def salam(): ...',
  },
  {
    id: 'py-10', type: 'single',
    question: 'Бул коддун жыйынтыгы кандай?\n\nx = [1, 2, 3]\nprint(x[-1])',
    options: opts('1', '3', '-1', 'Ката чыгат'),
    correctAnswer: 'b',
    explanation: 'Терс индекс тизменин аягынан эсептелет: x[-1] — акыркы элемент.',
  },
  {
    id: 'py-11', type: 'multiple',
    question: 'Кайсылары Python’до цикл түзөт?',
    options: opts('for', 'while', 'loop', 'repeat'),
    correctAnswer: ['a', 'b'],
    explanation: 'Python’до эки гана цикл бар: for жана while.',
  },
  {
    id: 'py-12', type: 'single',
    question: 'range(5) кайсы сандарды берет?',
    options: opts('1, 2, 3, 4, 5', '0, 1, 2, 3, 4', '0, 1, 2, 3, 4, 5', '5'),
    correctAnswer: 'b',
    explanation: 'range(n) 0дөн баштап n-1ге чейинки сандарды берет.',
  },
  {
    id: 'py-13', type: 'single',
    question: 'Ачкыч жок болсо ката бербей, сөздүктөн (dict) маани алуунун жолу кайсы?',
    options: opts('d[key]', 'd.get(key)', 'd.key', 'd.find(key)'),
    correctAnswer: 'b',
    explanation: 'd.get(key) ачкыч жок болсо None (же берилген демейки маанини) кайтарат, ал эми d[key] KeyError катасын берет.',
  },
  {
    id: 'py-14', type: 'text',
    question: 'Бул коддун жыйынтыгын жазыңыз:\n\nprint(2 ** 3)',
    correctAnswer: ['8'],
    explanation: '** — даражага көтөрүү: 2 · 2 · 2 = 8.',
  },
  {
    id: 'py-15', type: 'single',
    question: 'Шартты текшерүү үчүн кайсы конструкция колдонулат?',
    options: opts('if / elif / else', 'switch / case', 'when / then', 'check / other'),
    correctAnswer: 'a',
    explanation: 'Python’до шарт if, elif жана else аркылуу жазылат.',
  },
  {
    id: 'py-16', type: 'single',
    question: 'input() функциясы кайсы түрдөгү маанини кайтарат?',
    options: opts('int', 'str', 'float', 'bool'),
    correctAnswer: 'b',
    explanation: 'input() ар дайым сап (str) кайтарат. Сан керек болсо int() же float() менен өзгөртүү керек.',
  },
  {
    id: 'py-17', type: 'multiple',
    question: 'Кайсылары Python’догу логикалык операторлор?',
    options: opts('and', 'or', 'not', '&&'),
    correctAnswer: ['a', 'b', 'c'],
    explanation: 'Python’до логикалык операторлор сөз менен жазылат: and, or, not. && башка тилдерде колдонулат.',
  },
  {
    id: 'py-18', type: 'single',
    question: 'Бул коддун жыйынтыгы кандай?\n\nprint("Hi" * 3)',
    options: opts('HiHiHi', 'Hi3', 'Ката чыгат', 'Hi Hi Hi'),
    correctAnswer: 'a',
    explanation: 'Сапты санга көбөйткөндө ал ошончо жолу кайталанат.',
  },
  {
    id: 'py-19', type: 'code', language: 'python',
    question: 'Эки сандын суммасын кайтарган add(a, b) функциясын жазыңыз.',
    starterCode: 'def add(a, b):\n    pass',
    correctAnswer: 'def add(a, b):\n    return a + b',
    explanation: 'return ачкыч сөзү функциянын жыйынтыгын кайтарат.',
  },
  {
    id: 'py-20', type: 'single',
    question: 'Python’до комментарий кайсы белги менен башталат?',
    options: opts('//', '#', '<!-- -->', '--'),
    correctAnswer: 'b',
    explanation: '# белгисинен кийинки текст сап аягына чейин комментарий болуп эсептелет.',
  },
]

const webQuestions: Question[] = [
  {
    id: 'web-01', type: 'single',
    question: 'HTML кыскартуусу эмнени билдирет?',
    options: opts('HyperText Markup Language', 'High Tech Modern Language', 'Home Tool Markup Language', 'Hyperlink Text Mode Language'),
    correctAnswer: 'a',
    explanation: 'HTML — HyperText Markup Language, веб-барактын структурасын сүрөттөгөн белгилөө тили.',
  },
  {
    id: 'web-02', type: 'single',
    question: 'Шилтеме (ссылка) кайсы тег менен түзүлөт?',
    options: opts('<link>', '<href>', '<a>', '<url>'),
    correctAnswer: 'c',
    explanation: '<a href="..."> тегги шилтеме түзөт; <link> — CSS файлдарын туташтыруу үчүн.',
  },
  {
    id: 'web-03', type: 'single',
    question: 'Эң чоң аталыш кайсы тег?',
    options: opts('<h6>', '<head>', '<h1>', '<title>'),
    correctAnswer: 'c',
    explanation: '<h1> — биринчи деңгээлдеги, эң маанилүү аталыш.',
  },
  {
    id: 'web-04', type: 'multiple',
    question: 'Кайсылары CSS’те түс берүүнүн туура жолдору?',
    options: opts('#ff0000', 'rgb(255, 0, 0)', 'red', 'color(255)'),
    correctAnswer: ['a', 'b', 'c'],
    explanation: 'Түстү HEX (#ff0000), rgb() же атынан (red) берсе болот.',
  },
  {
    id: 'web-05', type: 'single',
    question: 'Flexbox’ту иштетүү үчүн контейнерге эмне жазылат?',
    options: opts('display: block', 'display: flex', 'flex: on', 'position: flex'),
    correctAnswer: 'b',
    explanation: 'display: flex контейнердин ичиндеги элементтерди flex-элементтерге айландырат.',
  },
  {
    id: 'web-06', type: 'text',
    question: 'CSS’те текстин түсүн өзгөрткөн касиеттин (property) атын жазыңыз.',
    correctAnswer: ['color'],
    explanation: 'color касиети тексттин түсүн берет, мисалы: color: navy;',
  },
  {
    id: 'web-07', type: 'single',
    question: 'id="title" элементин CSS’те кантип тандайбыз?',
    options: opts('.title', '#title', 'title', '*title'),
    correctAnswer: 'b',
    explanation: '# — id боюнча, . — класс боюнча тандайт.',
  },
  {
    id: 'web-08', type: 'single',
    question: 'Сүрөттү барака кошуу үчүн кайсы тег колдонулат?',
    options: opts('<picture-src>', '<img>', '<image>', '<photo>'),
    correctAnswer: 'b',
    explanation: '<img src="..." alt="..."> — сүрөт кошуучу тег; alt атрибуту сүрөттү сүрөттөйт.',
  },
]

export const trainingTests: Test[] = [
  {
    id: 'python-basics',
    title: 'Python негиздери',
    description: 'Өзгөрмөлөр, маалымат түрлөрү, операторлор, циклдер, функциялар жана тизмелер.',
    subject: 'Python',
    level: 'medium',
    topics: 'Бардык темалар',
    duration: 30,
    maxAttempts: null,
    showExplanation: true,
    questions: pythonQuestions,
    published: true,
  },
  {
    id: 'web-basics',
    title: 'HTML жана CSS негиздери',
    description: 'Теги, шилтемелер, селекторлор, түстөр жана Flexbox.',
    subject: 'HTML / CSS',
    level: 'easy',
    topics: 'HTML, CSS',
    duration: 12,
    maxAttempts: null,
    showExplanation: true,
    questions: webQuestions,
    published: true,
  },
]
