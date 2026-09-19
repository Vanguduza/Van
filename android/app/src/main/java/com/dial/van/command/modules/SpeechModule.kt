package com.dial.van.command.modules

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.dial.van.VanApplication
import com.dial.van.command.AdminCard
import com.dial.van.command.SectionHeader
import com.dial.van.command.TruthMessage
import com.dial.van.voice.SpeechContext

/**
 * Teaching VAN the words it keeps getting wrong.
 *
 * P2-AND-018. `PersonalSpeechModel` is constructed in `VanApplication` and *read* on every
 * voice turn — `biasingStrings` primes the recogniser and `correctionFor` rewrites the
 * transcript. `recordCorrection` and `pinTerm`, the only two ways anything gets into it,
 * had no caller. So VAN applied a personal speech model that could never learn a word, and
 * would mishear the same name every day forever.
 *
 * The correction is the owner's and only the owner's. `recordCorrection` refuses a trust
 * level below OWNER_CONFIRMED, which is why this is a screen rather than something the
 * recogniser infers from a retry: a model that teaches itself from its own second guess
 * learns its own mistakes.
 */
@Composable
internal fun SpeechModule(app: VanApplication, glass: com.dial.van.visual.VanGlassStyle) {
    val model = app.personalSpeechModel
    var heard by rememberSaveable { mutableStateOf("") }
    var meant by rememberSaveable { mutableStateOf("") }
    var term by rememberSaveable { mutableStateOf("") }
    var context by rememberSaveable { mutableStateOf(SpeechContext.GENERAL.name) }
    var message by remember { mutableStateOf<String?>(null) }

    val selected = remember(context) {
        SpeechContext.entries.firstOrNull { it.name == context } ?: SpeechContext.GENERAL
    }

    LazyColumn(
        modifier = Modifier.fillMaxSize().padding(horizontal = 14.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp),
        contentPadding = PaddingValues(vertical = 8.dp),
    ) {
        item { SectionHeader("Speech", "Words Van keeps getting wrong") }
        message?.let { item { TruthMessage(it) } }

        item {
            AdminCard(glass) {
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text("Correct a mishearing", color = Color.White, fontSize = 15.sp, fontWeight = FontWeight.Bold)
                    Text(
                        "Van will rewrite this in future transcripts, in the contexts you choose.",
                        color = Color(0xFFBCD1D8),
                        fontSize = 11.sp,
                    )
                    OutlinedTextField(
                        value = heard,
                        onValueChange = { heard = it },
                        modifier = Modifier.fillMaxWidth(),
                        label = { Text("Van heard") },
                        maxLines = 1,
                    )
                    OutlinedTextField(
                        value = meant,
                        onValueChange = { meant = it },
                        modifier = Modifier.fillMaxWidth(),
                        label = { Text("You said") },
                        maxLines = 1,
                    )
                    Button(onClick = {
                        // recordCorrection refuses a blank pair, an identical pair, and a
                        // trust level below OWNER_CONFIRMED. The screen reports what it
                        // decided rather than assuming it took.
                        val taught = model.recordCorrection(
                            observed = heard,
                            corrected = meant,
                            contexts = setOf(selected),
                        )
                        message = if (taught) {
                            heard = ""
                            meant = ""
                            "Van will hear that as \"$meant\" from now on."
                        } else {
                            "Nothing to learn there — the two need to differ, and neither can be empty."
                        }
                    }) { Text("Teach Van") }
                }
            }
        }

        item {
            AdminCard(glass) {
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text("Pin a word", color = Color.White, fontSize = 15.sp, fontWeight = FontWeight.Bold)
                    Text(
                        "A name or term Van should expect to hear, rather than one it got wrong.",
                        color = Color(0xFFBCD1D8),
                        fontSize = 11.sp,
                    )
                    OutlinedTextField(
                        value = term,
                        onValueChange = { term = it },
                        modifier = Modifier.fillMaxWidth(),
                        label = { Text("Word or name") },
                        maxLines = 1,
                    )
                    Button(onClick = {
                        val pinned = model.pinTerm(term, selected)
                        message = if (pinned) {
                            term = ""
                            "Van will listen for that."
                        } else {
                            "That needs a word."
                        }
                    }) { Text("Pin") }
                }
            }
        }

        item {
            AdminCard(glass) {
                Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
                    Text("Where it applies", color = Color.White, fontSize = 14.sp)
                    Text(
                        "A correction scoped to trading should not rewrite a message to a friend.",
                        color = Color(0xFFBCD1D8),
                        fontSize = 11.sp,
                    )
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        for (option in SpeechContext.entries.take(4)) {
                            Button(
                                onClick = { context = option.name },
                                colors = ButtonDefaults.buttonColors(
                                    containerColor = if (selected == option) {
                                        Color(0xFF2E6B7A)
                                    } else {
                                        Color(0xFF1E3A44)
                                    },
                                ),
                            ) { Text(option.name.lowercase().replaceFirstChar { it.uppercase() }) }
                        }
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        for (option in SpeechContext.entries.drop(4)) {
                            Button(
                                onClick = { context = option.name },
                                colors = ButtonDefaults.buttonColors(
                                    containerColor = if (selected == option) {
                                        Color(0xFF2E6B7A)
                                    } else {
                                        Color(0xFF1E3A44)
                                    },
                                ),
                            ) { Text(option.name.lowercase().replaceFirstChar { it.uppercase() }) }
                        }
                    }
                }
            }
        }
    }
}
