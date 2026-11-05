package com.dial.van.visual

import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.sp

/** Persistent truthful distinction inside the dedicated review package only. */
@Composable
fun VanCharacterReviewNotice() {
    if (VanCharacterAssets.reviewBuild) Text(VanCharacterReviewPolicy.LABEL,
        color = Color(0xFFFFC46B), fontSize = 11.sp,
        modifier = Modifier.semantics { contentDescription = VanCharacterReviewPolicy.LABEL })
}
