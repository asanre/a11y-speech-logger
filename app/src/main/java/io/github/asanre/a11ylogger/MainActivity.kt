package io.github.asanre.a11ylogger

import android.content.ComponentName
import android.os.Bundle
import android.view.accessibility.AccessibilityManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge

/** Intro and setup FAQ. Capturing works without opening it; it only documents how to use the app. */
class MainActivity : ComponentActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        val setup = Setup(
            packageName = packageName,
            focusLogger = ComponentName(this, FocusLoggerService::class.java).flattenToShortString(),
            talkBack = findTalkBack(),
        )
        setContent { AppTheme { HomeScreen(setup) } }
    }

    /** The installed TalkBack (Google's or a vendor fork such as Samsung's), as a short component name. */
    private fun findTalkBack(): String? =
        getSystemService(AccessibilityManager::class.java)
            .installedAccessibilityServiceList
            .map { it.resolveInfo.serviceInfo }
            .firstOrNull { "talkback" in it.packageName }
            ?.let { ComponentName(it.packageName, it.name).flattenToShortString() }
}
