package io.github.asanre.a11ylogger

import android.app.Activity
import android.content.Intent
import android.os.Bundle
import android.speech.tts.TextToSpeech.Engine

/** Answers the system's voice-data check so Settings accepts this engine as usable. */
class CheckVoiceDataActivity : Activity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val voices = arrayListOf("spa-ESP", "eng-USA")
        setResult(
            Engine.CHECK_VOICE_DATA_PASS,
            Intent()
                .putStringArrayListExtra(Engine.EXTRA_AVAILABLE_VOICES, voices)
                .putStringArrayListExtra(Engine.EXTRA_UNAVAILABLE_VOICES, arrayListOf()),
        )
        finish()
    }
}
