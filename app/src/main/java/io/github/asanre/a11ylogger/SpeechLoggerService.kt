package io.github.asanre.a11ylogger

import android.media.AudioFormat
import android.speech.tts.SynthesisCallback
import android.speech.tts.SynthesisRequest
import android.speech.tts.TextToSpeech
import android.speech.tts.TextToSpeechService

/**
 * Silent TTS engine: logs every utterance as a `[speech]` record and plays nothing.
 * Select it as the default engine and TalkBack's speech shows up in logcat.
 */
class SpeechLoggerService : TextToSpeechService() {

    private var language = arrayOf("spa", "ESP", "")

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
