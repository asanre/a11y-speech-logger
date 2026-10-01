package io.github.asanre.a11ylogger

import android.os.SystemClock
import android.util.Log

private const val TAG = "A11ySpeech"

/**
 * One record per line: `[kind] t=<elapsedRealtime ms> <fields>`. Both services run in the same
 * process, so `t` is comparable across focus, speech and window records.
 */
internal fun logA11y(kind: String, fields: String) {
    Log.i(TAG, "[$kind] t=${SystemClock.elapsedRealtime()} $fields")
}

/** Quotes a value on a single line so multi-line utterances don't break line-based parsing. */
internal fun CharSequence.quoted(): String =
    "\"" + toString().replace("\\", "\\\\").replace("\"", "\\\"").replace("\n", "\\n") + "\""
