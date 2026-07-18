const FALLBACK_TIME_ZONE = 'UTC'
const MAX_TIME_ZONE_LENGTH = 100

type IntlWithSupportedValues = typeof Intl & {
  supportedValuesOf?: (key: 'timeZone') => string[]
}

export function isValidTimeZone(value: string): boolean {
  const timeZone = value.trim()
  if (!timeZone || timeZone.length > MAX_TIME_ZONE_LENGTH) return false
  try {
    new Intl.DateTimeFormat('en', { timeZone }).format()
    return true
  } catch {
    return false
  }
}

export function getBrowserTimeZone(): string {
  try {
    const timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone?.trim()
    if (timeZone && isValidTimeZone(timeZone)) return timeZone
  } catch {
    // Privacy-focused browsers can omit or restrict locale information.
  }
  return FALLBACK_TIME_ZONE
}

export function getSupportedTimeZones(...additional: Array<string | undefined>): string[] {
  let supported: string[] = []
  try {
    supported = (Intl as IntlWithSupportedValues).supportedValuesOf?.('timeZone') || []
  } catch {
    supported = []
  }

  return Array.from(new Set([
    FALLBACK_TIME_ZONE,
    getBrowserTimeZone(),
    ...additional.filter((value): value is string => !!value && isValidTimeZone(value)),
    ...supported,
  ])).sort((left, right) => left.localeCompare(right))
}

export function formatCurrentTimeInZone(timeZone: string): string | null {
  if (!isValidTimeZone(timeZone)) return null
  return new Intl.DateTimeFormat(undefined, {
    timeZone,
    weekday: 'short',
    hour: 'numeric',
    minute: '2-digit',
    timeZoneName: 'short',
  }).format(new Date())
}
