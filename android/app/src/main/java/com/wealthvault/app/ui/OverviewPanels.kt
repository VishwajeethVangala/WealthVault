package com.wealthvault.app.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxHeight
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.wealthvault.app.data.ASSET_CLASS_LABEL
import com.wealthvault.app.data.HistoryPoint
import com.wealthvault.app.data.RiskResponse
import java.time.LocalDate
import kotlin.math.abs

/** Edit the target weight of each asset class; they should add up to 100%. */
@Composable
fun TargetsDialog(classes: List<String>, targets: Map<String, Double>, onSave: (Map<String, Double>) -> Unit, onDismiss: () -> Unit) {
    val values = remember { mutableStateMapOf<String, String>().apply { classes.forEach { c -> put(c, targets[c]?.let { v -> if (v % 1.0 == 0.0) v.toInt().toString() else v.toString() } ?: "") } } }
    val sum = values.values.sumOf { it.toDoubleOrNull() ?: 0.0 }
    val ok = abs(sum - 100) < 0.01
    AlertDialog(
        onDismissRequest = onDismiss,
        containerColor = Wv.c.surface,
        title = { Text("Target allocation", color = Wv.c.text) },
        text = {
            Column(Modifier.verticalScroll(rememberScrollState()), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                classes.forEach { c ->
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(ASSET_CLASS_LABEL[c] ?: c, style = Wv.body, color = Wv.c.text, modifier = Modifier.weight(1f))
                        OutlinedTextField(
                            values[c].orEmpty(), { v -> values[c] = v.filter { it.isDigit() || it == '.' }.take(5) },
                            suffix = { Text("%") }, singleLine = true,
                            keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal),
                            modifier = Modifier.width(110.dp),
                        )
                    }
                }
                Text(
                    if (ok) "Adds up to 100%." else String.format("Adds up to %.1f%%; make it 100%%.", sum),
                    style = Wv.small, color = if (ok) Wv.c.gain else Wv.c.warn,
                )
            }
        },
        confirmButton = {
            TextButton(enabled = ok, onClick = { onSave(values.mapValues { it.value.toDoubleOrNull() ?: 0.0 }.filterValues { it > 0 }) }) {
                Text("Save", color = if (ok) Wv.c.accent else Wv.c.text3)
            }
        },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel", color = Wv.c.text2) } },
    )
}
