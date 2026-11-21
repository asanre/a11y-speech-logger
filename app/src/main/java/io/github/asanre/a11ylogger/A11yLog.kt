package io.github.asanre.a11ylogger

import android.os.SystemClock
import android.util.Log

private const val TAG = "A11ySpeech"

// A log entry holds about 4 KB and a character takes up to three bytes.
private const val ENTRY_CHARS = 1000
private val entries = Any()

/**
 * One record per line: `[kind] t=<elapsedRealtime ms> <fields>`. Both services run in the same
 * process, so `t` is comparable across focus, speech and window records. A record longer than a log
 * entry continues in `[more] t=<same t> <rest>` entries, written together so no other record cuts in.
 */
internal fun logA11y(kind: String, fields: String) {
    val t = SystemClock.elapsedRealtime()
    val parts = "[$kind] t=$t $fields".chunked(ENTRY_CHARS)
    synchronized(entries) {
        Log.i(TAG, parts.first())
        parts.drop(1).forEach { Log.i(TAG, "[more] t=$t $it") }
    }
}

/** Quotes a value on a single line so multi-line utterances don't break line-based parsing. */
internal fun CharSequence.quoted(): String =
    "\"" + toString().replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n") + "\""
