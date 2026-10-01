package io.github.asanre.a11ylogger

import android.media.AudioFormat
import android.speech.tts.SynthesisCallback
import android.speech.tts.SynthesisRequest
import android.speech.tts.TextToSpeech
import android.speech.tts.TextToSpeechService
import java.util.Locale

/**
 * Silent TTS engine: logs every utterance as a `[speech]` record and plays nothing.
 * Select it as the default engine and TalkBack's speech shows up in logcat.
 */
class SpeechLoggerService : TextToSpeechService() {

    private var language = deviceLanguage().let { (lang, country) -> arrayOf(lang, country, "") }

    override fun onIsLanguageAvailable(lang: String?, country: String?, variant: String?): Int =
        TextToSpeech.LANG_COUNTRY_AVAILABLE

    override fun onGetLanguage(): Array<String> = language

    override fun onLoadLanguage(lang: String?, country: String?, variant: String?): Int {
        language = arrayOf(lang.orEmpty(), country.orEmpty(), variant.orEmpty())
        return TextToSpeech.LANG_COUNTRY_AVAILABLE
    }

    override fun onStop() = Unit

    override fun onSynthesizeText(request: SynthesisRequest, callback: SynthesisCallback) {
        logA11y("speech", request.charSequenceText.quoted())
        callback.start(SAMPLE_RATE, AudioFormat.ENCODING_PCM_16BIT, 1)
        // 10 ms of silence: an utterance with no audio at all risks being reported as an error,
        // which would make TalkBack fail over to another engine.
        callback.audioAvailable(SILENCE, 0, SILENCE.size)
        callback.done()
    }

    private companion object {
        const val SAMPLE_RATE = 16_000
        val SILENCE = ByteArray(SAMPLE_RATE / 100 * 2)
    }
}

/** The device locale as the ISO 639-2 / ISO 3166 alpha-3 pair TTS engines use, e.g. `eng` + `USA`. */
internal fun deviceLanguage(): Pair<String, String> {
    val locale = Locale.getDefault()
    return runCatching { locale.isO3Language to locale.isO3Country }.getOrDefault("eng" to "USA")
}
