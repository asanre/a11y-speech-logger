plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.compose.compiler)
}

android {
    namespace = "io.github.asanre.a11ylogger"
    compileSdk = 37

    defaultConfig {
        applicationId = "io.github.asanre.a11ylogger"
        minSdk = 26
        targetSdk = 36
        versionCode = 1
        versionName = "0.1"
    }

    buildFeatures {
        compose = true
    }
}

dependencies {
    implementation(platform(libs.compose.bom))
    implementation(libs.compose.material3)
    implementation(libs.compose.ui.tooling.preview)
    implementation(libs.activity.compose)
    debugImplementation(libs.compose.ui.tooling)
}
