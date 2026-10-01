package io.github.asanre.a11ylogger

import android.accessibilityservice.AccessibilityService
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.graphics.Rect
import android.os.Build
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import kotlin.math.roundToInt

/**
 * Runs next to TalkBack and logs, as records interleaved with [SpeechLoggerService]'s `[speech]`:
 * - `[focus]` every node that receives accessibility focus,
 * - `[window]` window and pane changes, `[announce]` announcements,
 * - `[tree]` the active window's node tree, on `adb shell am broadcast -a <ACTION_DUMP>`.
 */
class FocusLoggerService : AccessibilityService() {

    private val dumpReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) = dumpTree()
    }

    override fun onServiceConnected() {
        val filter = IntentFilter(ACTION_DUMP)
        if (Build.VERSION.SDK_INT >= 33) {
            registerReceiver(dumpReceiver, filter, RECEIVER_EXPORTED)
        } else {
            registerReceiver(dumpReceiver, filter)
        }
    }

    override fun onDestroy() {
        unregisterReceiver(dumpReceiver)
        super.onDestroy()
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent) {
        when (event.eventType) {
            AccessibilityEvent.TYPE_VIEW_ACCESSIBILITY_FOCUSED ->
                event.source?.let { logA11y("focus", "pkg=${it.packageName} ${it.describe()}") }
            AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED ->
                logA11y("window", "pkg=${event.packageName} class=${event.className} text=${event.joinedText()}")
            AccessibilityEvent.TYPE_ANNOUNCEMENT ->
                logA11y("announce", "pkg=${event.packageName} text=${event.joinedText()}")
        }
    }

    override fun onInterrupt() = Unit

    private fun AccessibilityEvent.joinedText(): String = text.joinToString(" | ").quoted()

    /** Logs the active window in tree order (not TalkBack's traversal order), skipping inert containers. */
    private fun dumpTree() {
        val root = rootInActiveWindow ?: return logA11y("tree", "no active window")
        logA11y("tree", "begin pkg=${root.packageName}")
        var count = 0
        fun visit(node: AccessibilityNodeInfo, depth: Int) {
            if (!node.isVisibleToUser) return
            if (node.isWorthLogging()) {
                count++
                val focused = if (node.isAccessibilityFocused) " FOCUSED" else ""
                logA11y("tree", "  ".repeat(depth) + node.describe() + focused)
            }
            for (i in 0 until node.childCount) node.getChild(i)?.let { visit(it, depth + 1) }
        }
        visit(root, 0)
        logA11y("tree", "end nodes=$count")
    }

    private fun AccessibilityNodeInfo.isWorthLogging(): Boolean =
        viewIdResourceName != null || !text.isNullOrEmpty() || !contentDescription.isNullOrEmpty() ||
            isClickable || isLongClickable || isFocusable || isCheckable

    private fun AccessibilityNodeInfo.describe(): String {
        val bounds = Rect().also(::getBoundsInScreen)
        val density = resources.displayMetrics.density
        val widthDp = (bounds.width() / density).roundToInt()
        val heightDp = (bounds.height() / density).roundToInt()
        val actionable = isClickable || isLongClickable
        val unlabeled = text.isNullOrBlank() && contentDescription.isNullOrBlank()
        val issues = buildList {
            if (actionable && unlabeled) {
                when {
                    childCount == 0 -> add("NO_LABEL")
                    hasLabelOnlyInIconChild() -> add("LABEL_IN_CHILD")
                }
            }
            if (actionable && minOf(widthDp, heightDp) < MIN_TOUCH_TARGET_DP) add("SMALL_TARGET")
            if (className?.toString() == EDIT_TEXT_CLASS && text.isNullOrEmpty() && hintTextOrNull().isNullOrEmpty()) {
                add("EDIT_NO_HINT")
            }
        }
        return listOfNotNull(
            "id=${viewIdResourceName ?: "-"}",
            "class=${className?.toString()?.substringAfterLast('.')}",
            text?.let { "text=${it.quoted()}" },
            contentDescription?.let { "desc=${it.quoted()}" },
            extras.getCharSequence(EXTRA_ROLE_DESCRIPTION)?.let { "role=${it.quoted()}" },
            stateDescriptionOrNull()?.let { "state=${it.quoted()}" },
            hintTextOrNull()?.let { "hint=${it.quoted()}" },
            error?.let { "error=${it.quoted()}" },
            if (isCheckable) "checked=$isChecked" else null,
            "heading".takeIf { Build.VERSION.SDK_INT >= 28 && isHeading },
            "selected".takeIf { isSelected },
            "disabled".takeIf { !isEnabled },
            "clickable".takeIf { isClickable },
            "longclickable".takeIf { isLongClickable },
            actionList.mapNotNull { it.label }.takeIf { it.isNotEmpty() }
                ?.let { "actions=${it.joinToString("|").quoted()}" },
            "bounds=${bounds.toShortString()}",
            "size=${widthDp}x${heightDp}dp",
            issues.takeIf { it.isNotEmpty() }?.let { "issues=${it.joinToString(",")}" },
        ).joinToString(" ")
    }

    /**
     * The label sits on a non-actionable descendant that has only a content description, the shape of
     * an icon button whose description is on the icon, however deep the icon is wrapped. Descendants
     * with text are left out: a clickable row of text views is the normal View pattern and TalkBack
     * reads it fine.
     */
    private fun AccessibilityNodeInfo.hasLabelOnlyInIconChild(): Boolean {
        val inner = innerDescendants().toList()
        return inner.none { !it.text.isNullOrBlank() } && inner.any { !it.contentDescription.isNullOrBlank() }
    }

    /** Descendants down to, not into, nested actionable nodes: those are controls of their own. */
    private fun AccessibilityNodeInfo.innerDescendants(): Sequence<AccessibilityNodeInfo> =
        (0 until childCount).asSequence()
            .mapNotNull(::getChild)
            .filterNot { it.isClickable || it.isLongClickable }
            .flatMap { sequenceOf(it) + it.innerDescendants() }

    private fun AccessibilityNodeInfo.stateDescriptionOrNull(): CharSequence? =
        if (Build.VERSION.SDK_INT >= 30) stateDescription else null

    private fun AccessibilityNodeInfo.hintTextOrNull(): CharSequence? =
        if (Build.VERSION.SDK_INT >= 26) hintText else null

    companion object {
        const val ACTION_DUMP = "io.github.asanre.a11ylogger.DUMP"
        private const val EXTRA_ROLE_DESCRIPTION = "AccessibilityNodeInfo.roleDescription"
        private const val MIN_TOUCH_TARGET_DP = 48
        private const val EDIT_TEXT_CLASS = "android.widget.EditText"
    }
}
