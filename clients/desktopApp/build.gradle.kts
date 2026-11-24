import org.gradle.jvm.toolchain.JavaLanguageVersion

plugins {
    kotlin("jvm")
    id("org.jetbrains.compose")
    id("org.jetbrains.kotlin.plugin.compose")
}

kotlin {
    jvmToolchain(21)
}

val java21Home = javaToolchains
    .launcherFor { languageVersion.set(JavaLanguageVersion.of(21)) }
    .get()
    .metadata
    .installationPath
    .asFile
    .absolutePath

dependencies {
    implementation(project(":shared"))
    implementation(compose.desktop.currentOs)
    implementation(compose.material3)
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-swing:1.11.0")
}

// AG-UI 0.4.1 is built against kotlinx-datetime 0.6.x. Compose Material3
// pulls 0.7.x, where Clock moved; keep the SDK's expected API at runtime.
configurations.all {
    resolutionStrategy.force(
        "org.jetbrains.kotlinx:kotlinx-datetime:0.6.2",
        "org.jetbrains.kotlinx:kotlinx-datetime-jvm:0.6.2",
    )
}

compose.desktop {
    application {
        mainClass = "ai.grid.desktop.MainKt"
        javaHome = java21Home
    }
}
