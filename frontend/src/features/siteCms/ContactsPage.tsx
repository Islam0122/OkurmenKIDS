import { ContentListPage } from './ContentListPage'
import { SettingsForm, type SettingField } from './SettingsForm'
import { CmsPage, Panel } from './ui'

const CONTACTS: SettingField[] = [
  { name: 'phone', label: 'Телефон', type: 'tel', placeholder: '+996 …' },
  { name: 'whatsapp', label: 'WhatsApp (номер)', type: 'tel', placeholder: '+996 …' },
  { name: 'telegram', label: 'Telegram', placeholder: '@okurmenkids или ссылка' },
  { name: 'email', label: 'E-mail', type: 'email' },
  { name: 'working_hours', label: 'Часы работы', placeholder: 'Пн–Сб 9:00–19:00', wide: true },
]

/** /marketing/site/contacts — контакты в шапке, подвале и на странице «Контакты», филиалы. */
export function ContactsPage() {
  return (
    <CmsPage title="Контактная информация" description="Телефон и мессенджеры показываются в подвале, на странице «Контакты» и в форме записи. Соцсети — в «Настройки → Социальные ссылки».">
      <SettingsForm title="Контакты академии" fields={CONTACTS} />
      <Panel title="Филиалы" description="Адреса, телефоны и карта для каждого филиала">
        <ContentListPage resource="branches" embedded />
      </Panel>
    </CmsPage>
  )
}
