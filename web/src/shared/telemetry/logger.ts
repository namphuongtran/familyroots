/**
 * Structured logging for the web client.
 *
 * One record per event with a stable `event` name, so logs can be queried rather
 * than read. `traceId` is what ties a browser record to the backend's JSON log
 * line for the same request.
 *
 * Replaces ad-hoc console.log: a bare string cannot be searched, aggregated, or
 * correlated.
 */

export type LogLevel = 'debug' | 'info' | 'warn' | 'error'

export interface LogFields {
  traceId?: string | null
  route?: string
  clanId?: string | null
  [key: string]: unknown
}

export interface LogRecord extends LogFields {
  level: LogLevel
  event: string
  time: string
}

export type LogSink = (record: LogRecord) => void

const ORDER: Record<LogLevel, number> = { debug: 10, info: 20, warn: 30, error: 40 }

function consoleSink(record: LogRecord): void {
  const method = record.level === 'debug' ? 'log' : record.level
  console[method](`[${record.event}]`, record)
}

export interface LoggerOptions {
  sink?: LogSink
  level?: LogLevel
}

export interface Logger {
  debug(event: string, fields?: LogFields): void
  info(event: string, fields?: LogFields): void
  warn(event: string, fields?: LogFields): void
  error(event: string, fields?: LogFields): void
}

export function createLogger(options: LoggerOptions = {}): Logger {
  const sink = options.sink ?? consoleSink
  const threshold = ORDER[options.level ?? 'debug']

  const emit = (level: LogLevel, event: string, fields?: LogFields): void => {
    if (ORDER[level] < threshold) return
    try {
      sink({ ...fields, level, event, time: new Date().toISOString() })
    } catch {
      // Telemetry must never break the feature it observes.
    }
  }

  return {
    debug: (event, fields) => emit('debug', event, fields),
    info: (event, fields) => emit('info', event, fields),
    warn: (event, fields) => emit('warn', event, fields),
    error: (event, fields) => emit('error', event, fields),
  }
}

/** App-wide logger: everything in dev, warnings and errors in production. */
export const logger = createLogger({
  level: process.env.NODE_ENV === 'production' ? 'warn' : 'debug',
})
