package com.dial.van.visual

import androidx.compose.material3.Text
import androidx.compose.material3.MaterialTheme
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.padding
import androidx.compose.ui.unit.dp
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.sp

/** Persistent truthful distinction inside the dedicated review package only. */
@Composable
fun VanCharacterReviewNotice(modifier: Modifier = Modifier) {
    if (VanCharacterAssets.reviewBuild) Text(VanCharacterReviewPolicy.LABEL,
        color = MaterialTheme.colorScheme.onSurfaceVariant, fontSize = 11.sp,
        modifier = modifier.background(MaterialTheme.colorScheme.surfaceVariant).padding(horizontal = 6.dp, vertical = 3.dp)
            .semantics { contentDescription = VanCharacterReviewPolicy.LABEL })
}
