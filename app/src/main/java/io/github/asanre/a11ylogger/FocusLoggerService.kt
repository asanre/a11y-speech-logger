package io.github.asanre.a11ylogger

import android.accessibilityservice.AccessibilityService
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.graphics.Bitmap
import android.graphics.Rect
import android.os.Build
import android.view.Display
import android.view.View
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import com.google.android.apps.common.testing.accessibility.framework.AccessibilityCheckPreset
import com.google.android.apps.common.testing.accessibility.framework.AccessibilityCheckResult.AccessibilityCheckResultType
import com.google.android.apps.common.testing.accessibility.framework.AccessibilityHierarchyCheckResult
import com.google.android.apps.common.testing.accessibility.framework.Parameters
import com.google.android.apps.common.testing.accessibility.framework.uielement.AccessibilityHierarchyAndroid
import com.google.android.apps.common.testing.accessibility.framework.uielement.ViewHierarchyElement
import com.google.android.apps.common.testing.accessibility.framework.utils.contrast.BitmapImage
import java.util.Locale
import kotlin.math.roundToInt

/**
 * Runs next to TalkBack and logs, as records interleaved with [SpeechLoggerService]'s `[speech]`:
 * - `[focus]` every node that receives accessibility focus, `[input]` every node that receives input focus,
 * - `[click]` every node activated,
 * - `[window]` window and pane changes, `[announce]` announcements,
 * - `[tree]` the active window's node tree, on `adb shell am broadcast -a <ACTION_DUMP>`,
 * - `[atf]` the Accessibility Test Framework results on that window, when the broadcast adds `--ez atf true`.
 *
 * On `adb shell am broadcast -a <ACTION_FOCUS_WINDOW>` it moves accessibility focus into the active window: see
 * [focusActiveWindow]. On `<ACTION_ACTIVATE>` it clicks the node TalkBack has focus on, as a double tap does.
 */
class FocusLoggerService : AccessibilityService() {

    private val dumpReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context, intent: Intent) {
            when (intent.action) {
                ACTION_FOCUS_WINDOW -> return focusActiveWindow()
                ACTION_ACTIVATE -> return activateFocused()
            }
            dumpTree()
            if (intent.getBooleanExtra(EXTRA_ATF, false)) checkWithAtf()
        }
    }

    override fun onServiceConnected() {
        val filter = IntentFilter(ACTION_DUMP).apply {
            addAction(ACTION_FOCUS_WINDOW)
            addAction(ACTION_ACTIVATE)
        }
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
            AccessibilityEvent.TYPE_VIEW_FOCUSED ->
                event.source?.let { logA11y("input", "pkg=${it.packageName} ${it.describe()}") }
            AccessibilityEvent.TYPE_VIEW_CLICKED ->
                event.source?.let { logA11y("click", "pkg=${it.packageName} ${it.describe()}") }
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
        // Always written, empty when the window has no title, so a missing title is told from an older log.
        val title = windows.firstOrNull { it.isActive }?.title ?: ""
        logA11y("tree", "begin pkg=${root.packageName} window=${title.quoted()}")
        var count = 0
        fun visit(node: AccessibilityNodeInfo, depth: Int) {
            if (!node.isVisibleToUser) return
            if (node.isWorthLogging()) {
                count++
                val focused = if (node.isAccessibilityFocused) " FOCUSED" else ""
                val inputFocused = if (node.isFocused) " INPUT_FOCUSED" else ""
                logA11y("tree", "  ".repeat(depth) + node.describe() + focused + inputFocused)
            }
            for (i in 0 until node.childCount) node.getChild(i)?.let { visit(it, depth + 1) }
        }
        visit(root, 0)
        logA11y("tree", "end nodes=$count")
    }

    /**
     * Moves accessibility focus to the last node of the active window. TalkBack's "first item" shortcut works
     * within the window that has focus, which can be the navigation bar; from here it reaches the app's first
     * item, and always as a move, so the walk's first element gets a `[focus]` of its own.
     */
    private fun focusActiveWindow() {
        val root = rootInActiveWindow ?: return
        var last: AccessibilityNodeInfo? = null
        fun visit(node: AccessibilityNodeInfo) {
            if (!node.isVisibleToUser) return
            if (node.isWorthLogging()) last = node
            for (i in 0 until node.childCount) node.getChild(i)?.let(::visit)
        }
        visit(root)
        last?.performAction(AccessibilityNodeInfo.ACTION_ACCESSIBILITY_FOCUS)
    }

    /**
     * A double tap makes TalkBack click the node it has focus on. Its keyboard shortcut for that needs a keyboard
     * with letters, which recreates the activity on screen when it is connected, so the click is done here.
     */
    private fun activateFocused() {
        findFocus(AccessibilityNodeInfo.FOCUS_ACCESSIBILITY)?.performAction(AccessibilityNodeInfo.ACTION_CLICK)
    }

    /**
     * Runs the checks of the Accessibility Test Framework, the ones Accessibility Scanner and Compose's
     * `enableAccessibilityChecks()` run, and logs errors and warnings, then `[atf] end`. The contrast checks
     * measure a screenshot, which an accessibility service can take from API 30.
     */
    private fun checkWithAtf() {
        val root = rootInActiveWindow ?: return logA11y("atf", "end results=0 error=\"no active window\"")
        if (Build.VERSION.SDK_INT < 30) return runAtf(root, null, "no screenshot below API 30")
        takeScreenshot(Display.DEFAULT_DISPLAY, mainExecutor, object : TakeScreenshotCallback {
            override fun onSuccess(screenshot: ScreenshotResult) {
                val bitmap = screenshot.hardwareBuffer.use { buffer ->
                    Bitmap.wrapHardwareBuffer(buffer, screenshot.colorSpace)?.copy(Bitmap.Config.ARGB_8888, false)
                }
                runAtf(root, bitmap, "screenshot not readable".takeIf { bitmap == null })
            }

            override fun onFailure(errorCode: Int) = runAtf(root, null, "screenshot failed with error $errorCode")
        })
    }

    /** Without a screenshot ATF skips the contrast checks: [noScreenshot] says why, so it is not read as a pass. */
    private fun runAtf(root: AccessibilityNodeInfo, screenshot: Bitmap?, noScreenshot: String?) {
        runCatching<List<AccessibilityHierarchyCheckResult>> {
            val hierarchy = AccessibilityHierarchyAndroid.newBuilder(root, this).build()
            val parameters = Parameters().apply { screenshot?.let { putScreenCapture(BitmapImage(it)) } }
            AccessibilityCheckPreset.getAccessibilityHierarchyChecksForPreset(AccessibilityCheckPreset.LATEST)
                .flatMap { it.runCheckOnHierarchy(hierarchy, null, parameters) }
                .filter { it.type in REPORTED_ATF_TYPES }
        }.onSuccess { results ->
            results.forEach { logA11y("atf", it.describe()) }
            val skipped = noScreenshot?.let { " skipped=contrast reason=${it.quoted()}" } ?: ""
            logA11y("atf", "end results=${results.size}$skipped")
        }.onFailure {
            logA11y("atf", "end results=0 error=${it.toString().quoted()}")
        }
    }

    /** Same `id`, `class` and `bounds` format as [describe], so a result can be matched to its tree node. */
    private fun AccessibilityHierarchyCheckResult.describe(): String = listOfNotNull(
        "check=${sourceCheckClass.simpleName}",
        "type=$type",
        element?.describe(),
        "msg=${getMessage(Locale.ENGLISH).quoted()}",
    ).joinToString(" ")

    private fun ViewHierarchyElement.describe(): String =
        "id=${resourceName ?: "-"} class=${className?.toString()?.substringAfterLast('.')} " +
            boundsInScreen.run { "bounds=[$left,$top][$right,$bottom]" }

    /**
     * Nodes that carry something TalkBack reads or acts on. Includes nodes that only carry a role: Compose
     * puts the role of a node with children of its own on such a child, and TalkBack reads it as content.
     */
    private fun AccessibilityNodeInfo.isWorthLogging(): Boolean =
        viewIdResourceName != null || !text.isNullOrEmpty() || !contentDescription.isNullOrEmpty() ||
            isClickable || isLongClickable || isFocusable || isCheckable ||
            className?.toString() in ROLE_CLASSES || !extras.getCharSequence(EXTRA_ROLE_DESCRIPTION).isNullOrEmpty() ||
            collectionInfo != null || paneTitleOrNull() != null || liveRegion != View.ACCESSIBILITY_LIVE_REGION_NONE

    private fun AccessibilityNodeInfo.describe(): String {
        val bounds = Rect().also(::getBoundsInScreen)
        val density = resources.displayMetrics.density
        val widthDp = (bounds.width() / density).roundToInt()
        val heightDp = (bounds.height() / density).roundToInt()
        val actionable = isClickable || isLongClickable
        val unlabeled = text.isNullOrBlank() && contentDescription.isNullOrBlank()
        val issues = buildList {
            if (actionable && unlabeled) labelIssue()?.let(::add)
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
            expandedOrNull()?.let { "expanded=$it" },
            "required".takeIf { Build.VERSION.SDK_INT >= 36 && isFieldRequired },
            "heading".takeIf { Build.VERSION.SDK_INT >= 28 && isHeading },
            "selected".takeIf { isSelected },
            "disabled".takeIf { !isEnabled },
            paneTitleOrNull()?.let { "pane=${it.quoted()}" },
            LIVE_REGIONS[liveRegion]?.let { "live=$it" },
            collectionInfo?.let { "collection=${it.rowCount}x${it.columnCount}" },
            collectionItemInfo?.let { "item=${it.rowIndex},${it.columnIndex}" },
            "scrollable".takeIf { isScrollable },
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
     * Where an unlabeled actionable node can take its name from, among its non-actionable descendants:
     * - nowhere, `NO_LABEL`: no descendant has text or a description, so TalkBack has nothing to read
     *   (descendants hidden from accessibility, or decorative only);
     * - content descriptions only, `LABEL_IN_CHILD`: an icon button whose description is on the icon,
     *   however deep the icon is wrapped. With text it is a clickable row of text views, the normal View
     *   pattern, and TalkBack reads it fine.
     */
    private fun AccessibilityNodeInfo.labelIssue(): String? {
        val inner = innerDescendants().toList()
        val hasText = inner.any { !it.text.isNullOrBlank() }
        val hasDescription = inner.any { !it.contentDescription.isNullOrBlank() }
        return when {
            !hasText && !hasDescription -> "NO_LABEL"
            !hasText -> "LABEL_IN_CHILD"
            else -> null
        }
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

    private fun AccessibilityNodeInfo.paneTitleOrNull(): CharSequence? =
        if (Build.VERSION.SDK_INT >= 28) paneTitle?.takeIf { it.isNotEmpty() } else null

    private fun AccessibilityNodeInfo.expandedOrNull(): String? =
        if (Build.VERSION.SDK_INT >= 36) EXPANDED_STATES[expandedState] else null

    companion object {
        const val ACTION_DUMP = "io.github.asanre.a11ylogger.DUMP"
        const val ACTION_FOCUS_WINDOW = "io.github.asanre.a11ylogger.FOCUS_WINDOW"
        const val ACTION_ACTIVATE = "io.github.asanre.a11ylogger.ACTIVATE"
        private const val EXTRA_ATF = "atf"
        private val REPORTED_ATF_TYPES = setOf(AccessibilityCheckResultType.ERROR, AccessibilityCheckResultType.WARNING)
        private const val EXTRA_ROLE_DESCRIPTION = "AccessibilityNodeInfo.roleDescription"
        private const val MIN_TOUCH_TARGET_DP = 48
        private const val EDIT_TEXT_CLASS = "android.widget.EditText"
        private val ROLE_CLASSES = setOf(
            "android.widget.Button", "android.widget.ImageButton", "android.widget.CheckBox",
            "android.widget.RadioButton", "android.widget.Switch", "android.widget.ToggleButton",
            "android.widget.Spinner", "android.widget.SeekBar", "android.widget.ProgressBar",
            "android.widget.ImageView", EDIT_TEXT_CLASS,
        )
        private val LIVE_REGIONS = mapOf(
            View.ACCESSIBILITY_LIVE_REGION_POLITE to "polite",
            View.ACCESSIBILITY_LIVE_REGION_ASSERTIVE to "assertive",
        )
        private val EXPANDED_STATES = mapOf(
            AccessibilityNodeInfo.EXPANDED_STATE_COLLAPSED to "collapsed",
            AccessibilityNodeInfo.EXPANDED_STATE_PARTIAL to "partial",
            AccessibilityNodeInfo.EXPANDED_STATE_FULL to "full",
        )
    }
}
