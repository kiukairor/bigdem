import { MicroAgent } from '@newrelic/browser-agent/loaders/micro-agent'

let started = false

export function initNRMicroAgent() {
  if (started || typeof window === 'undefined') return
  const licenseKey = process.env.NEXT_PUBLIC_NR_BROWSER_LICENSE_KEY
  const appId     = process.env.NEXT_PUBLIC_NR_BROWSER_APP_ID
  const accountId = process.env.NEXT_PUBLIC_NR_BROWSER_ACCOUNT_ID
  const trustKey  = process.env.NEXT_PUBLIC_NR_BROWSER_TRUST_KEY || accountId
  if (!licenseKey || !appId || !accountId) return
  new MicroAgent({
    init: {
      distributed_tracing: { enabled: true },
      privacy: { cookies_enabled: true },
      ajax: { deny_list: ['bam.eu01.nr-data.net'] },
    },
    info: {
      beacon: 'bam.eu01.nr-data.net',
      errorBeacon: 'bam.eu01.nr-data.net',
      licenseKey,
      applicationID: appId,
      sa: 1,
    },
    loader_config: {
      accountID: accountId,
      trustKey,
      agentID: appId,
      licenseKey,
      applicationID: appId,
    },
  })
  started = true
}
