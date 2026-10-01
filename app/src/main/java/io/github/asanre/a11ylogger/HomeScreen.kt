package io.github.asanre.a11ylogger

import android.content.ActivityNotFoundException
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import android.content.Intent
import android.os.Build
import android.provider.Settings
import android.widget.Toast
import androidx.annotation.StringRes
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.isSystemInDarkTheme
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.ColumnScope
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawing
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.dynamicDarkColorScheme
import androidx.compose.material3.dynamicLightColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp

/** What the FAQ needs to build exact adb commands for this device. */
data class Setup(
    val packageName: String,
    val focusLogger: String,
    val talkBack: String?,
    /** Accessibility services enabled right now, as short component names. */
    val enabledServices: List<String>,
)

// Fallback when no TalkBack is installed; vendor builds are detected at runtime.
private const val GOOGLE_TALKBACK = "com.google.android.marvin.talkback/.TalkBackService"
// Not a public constant, but the action Settings registers for its text-to-speech screen.
private const val ACTION_TTS_SETTINGS = "com.android.settings.TTS_SETTINGS"

@Composable
fun HomeScreen(setup: Setup) {
    val talkBack = setup.talkBack ?: GOOGLE_TALKBACK
    val ours = listOf(talkBack, setup.focusLogger)
    // Keep whatever else the user has enabled; the setting is a single colon-separated list.
    val servicesOn = (setup.enabledServices + ours).distinct().joinToString(":")
    val servicesOff = (setup.enabledServices - ours.toSet()).joinToString(":")
    Surface(Modifier.fillMaxSize()) {
        LazyColumn(
            modifier = Modifier.windowInsetsPadding(WindowInsets.safeDrawing),
            contentPadding = PaddingValues(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            item {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(
                        text = stringResource(R.string.intro_title),
                        style = MaterialTheme.typography.headlineSmall,
                        modifier = Modifier.semantics { heading() },
                    )
                    Text(stringResource(R.string.intro_body), style = MaterialTheme.typography.bodyLarge)
                }
            }
            item {
                Text(
                    text = stringResource(R.string.faq_title),
                    style = MaterialTheme.typography.titleLarge,
                    modifier = Modifier.padding(top = 8.dp).semantics { heading() },
                )
            }
            item {
                FaqItem(R.string.faq_what_q) { Paragraph(R.string.faq_what_a) }
            }
            item {
                FaqItem(R.string.faq_tts_q) {
                    Paragraph(R.string.faq_tts_a)
                    SettingsButton(R.string.open_tts_settings, ACTION_TTS_SETTINGS)
                    Paragraph(R.string.faq_tts_adb)
                    Command("adb shell settings put secure tts_default_synth ${setup.packageName}")
                    Paragraph(R.string.faq_tts_after)
                }
            }
            item {
                FaqItem(R.string.faq_service_q) {
                    Paragraph(R.string.faq_service_a)
                    SettingsButton(R.string.open_accessibility_settings, Settings.ACTION_ACCESSIBILITY_SETTINGS)
                }
            }
            item {
                FaqItem(R.string.faq_talkback_q) {
                    Text(
                        if (setup.talkBack != null) {
                            stringResource(R.string.faq_talkback_detected, setup.talkBack)
                        } else {
                            stringResource(R.string.faq_talkback_not_found)
                        },
                        style = MaterialTheme.typography.bodyMedium,
                    )
                    Paragraph(R.string.faq_talkback_on)
                    Command("adb shell settings put secure enabled_accessibility_services $servicesOn")
                    Command("adb shell settings put secure accessibility_enabled 1")
                    Paragraph(R.string.faq_talkback_off)
                    Command(
                        if (servicesOff.isEmpty()) {
                            "adb shell settings delete secure enabled_accessibility_services"
                        } else {
                            "adb shell settings put secure enabled_accessibility_services $servicesOff"
                        },
                    )
                    Paragraph(R.string.faq_talkback_note)
                }
            }
            item {
                FaqItem(R.string.faq_capture_q) {
                    Paragraph(R.string.faq_capture_clear)
                    Command("adb logcat -c")
                    Paragraph(R.string.faq_capture_dump)
                    Command("adb shell am broadcast -a ${FocusLoggerService.ACTION_DUMP}")
                    Paragraph(R.string.faq_capture_save)
                    Command("adb logcat -d -s A11ySpeech:I -v raw > session.txt")
                    Paragraph(R.string.faq_capture_tool)
                }
            }
            item {
                FaqItem(R.string.faq_restore_q) {
                    Paragraph(R.string.faq_restore_tts)
                    Command("adb shell settings delete secure tts_default_synth")
                    Paragraph(R.string.faq_restore_service)
                    Command("adb uninstall ${setup.packageName}")
                }
            }
        }
    }
}

@Composable
private fun FaqItem(@StringRes question: Int, content: @Composable ColumnScope.() -> Unit) {
    var expanded by rememberSaveable { mutableStateOf(false) }
    val state = stringResource(if (expanded) R.string.expanded else R.string.collapsed)
    Card(Modifier.fillMaxWidth()) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .clickable(onClickLabel = stringResource(if (expanded) R.string.collapse else R.string.expand)) {
                    expanded = !expanded
                }
                .semantics {
                    heading()
                    stateDescription = state
                }
                .padding(16.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(
                text = stringResource(question),
                style = MaterialTheme.typography.titleMedium,
                modifier = Modifier.weight(1f),
            )
            Text(
                text = if (expanded) "−" else "+",
                style = MaterialTheme.typography.titleLarge,
                modifier = Modifier.clearAndSetSemantics {},
            )
        }
        AnimatedVisibility(expanded) {
            Column(
                modifier = Modifier.padding(start = 16.dp, end = 16.dp, bottom = 16.dp),
                verticalArrangement = Arrangement.spacedBy(8.dp),
                content = content,
            )
        }
    }
}

@Composable
private fun SettingsButton(@StringRes text: Int, action: String) {
    val context = LocalContext.current
    OutlinedButton(
        onClick = {
            try {
                context.startActivity(Intent(action))
            } catch (_: ActivityNotFoundException) {
                context.startActivity(Intent(Settings.ACTION_SETTINGS))
            }
        },
    ) {
        Text(stringResource(text))
    }
}

@Composable
private fun Paragraph(@StringRes text: Int) {
    Text(stringResource(text), style = MaterialTheme.typography.bodyMedium)
}

/** A command the whole row copies on click; TalkBack reads the command, then "double tap to copy command". */
@Composable
private fun Command(command: String) {
    val context = LocalContext.current
    Row(
        modifier = Modifier
            .fillMaxWidth()
            .clip(MaterialTheme.shapes.small)
            .background(MaterialTheme.colorScheme.surface)
            .clickable(onClickLabel = stringResource(R.string.copy_command)) { context.copyToClipboard(command) }
            .padding(12.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text(
            text = command,
            style = MaterialTheme.typography.bodySmall,
            fontFamily = FontFamily.Monospace,
            modifier = Modifier.weight(1f),
        )
        Text(
            text = stringResource(R.string.copy),
            style = MaterialTheme.typography.labelLarge,
            color = MaterialTheme.colorScheme.primary,
            modifier = Modifier.clearAndSetSemantics {},
        )
    }
}

private fun Context.copyToClipboard(text: String) {
    getSystemService(ClipboardManager::class.java).setPrimaryClip(ClipData.newPlainText("adb command", text))
    // Android 13+ shows its own confirmation.
    if (Build.VERSION.SDK_INT < 33) Toast.makeText(this, R.string.copied, Toast.LENGTH_SHORT).show()
}

@Composable
fun AppTheme(content: @Composable () -> Unit) {
    val dark = isSystemInDarkTheme()
    val context = LocalContext.current
    val colors = when {
        Build.VERSION.SDK_INT >= 31 -> if (dark) dynamicDarkColorScheme(context) else dynamicLightColorScheme(context)
        dark -> darkColorScheme()
        else -> lightColorScheme()
    }
    MaterialTheme(colorScheme = colors, content = content)
}

@Preview
@Composable
private fun HomeScreenPreview() {
    AppTheme {
        HomeScreen(
            Setup(
                packageName = "io.github.asanre.a11ylogger",
                focusLogger = "io.github.asanre.a11ylogger/.FocusLoggerService",
                talkBack = GOOGLE_TALKBACK,
                enabledServices = emptyList(),
            ),
        )
    }
}
