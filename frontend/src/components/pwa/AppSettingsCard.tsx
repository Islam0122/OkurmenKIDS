import { AppSettingsPanel } from './AppSettingsPanel'

/** The compact «Приложение» section for profile/settings pages. */
export function AppSettingsCard() {
  return (
    <section className="card card-body mt-6" aria-labelledby="app-settings-title">
      <h2 id="app-settings-title" className="section-title mb-4">
        Приложение и уведомления
      </h2>
      <AppSettingsPanel />
    </section>
  )
}
