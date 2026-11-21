package io.github.asanre.a11ylogger.sample

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.safeDrawingPadding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.material3.TextField
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.tooling.preview.Preview
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

private const val REPLY_DELAY_MS = 1500L

@Composable
fun SupportScreen() {
    var conversation by remember { mutableStateOf(initialConversation()) }
    var unreadOnly by remember { mutableStateOf(false) }
    var noticeVisible by remember { mutableStateOf(true) }
    val scope = rememberCoroutineScope()

    Column(
        Modifier
            .fillMaxSize()
            .background(Color.White)
            .safeDrawingPadding()
            .padding(horizontal = 16.dp),
    ) {
        Text("Soporte", style = MaterialTheme.typography.headlineSmall, modifier = Modifier.padding(vertical = 12.dp))
        if (noticeVisible) Notice(onClose = { noticeVisible = false })
        Filters(unreadOnly = unreadOnly, onChange = { unreadOnly = it })
        Text(
            "Ver mis pedidos",
            color = MaterialTheme.colorScheme.primary,
            modifier = Modifier
                .clickable { }
                .padding(vertical = 12.dp),
        )
        Messages(conversation.messages, Modifier.weight(1f))
        Options(conversation.options) { option ->
            scope.launch {
                delay(REPLY_DELAY_MS)
                conversation = conversation.answered(option)
            }
        }
        Composer()
    }
}

@Composable
private fun Notice(onClose: () -> Unit) {
    Row(
        Modifier
            .fillMaxWidth()
            .background(Color(0xFFF5F5F5), RoundedCornerShape(8.dp))
            .padding(12.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text("Horario de atención: de 9 a 18 h", color = Color(0xFFBDBDBD), modifier = Modifier.weight(1f))
        Box(
            Modifier
                .size(20.dp)
                .background(Color(0xFF616161), CircleShape)
                .clickable(role = Role.Button, onClick = onClose)
                .semantics { contentDescription = "Cerrar aviso" },
        )
    }
}

@Composable
private fun Filters(unreadOnly: Boolean, onChange: (Boolean) -> Unit) {
    Row(Modifier.padding(vertical = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        Filter("Todos", active = !unreadOnly) { onChange(false) }
        Filter("Sin leer", active = unreadOnly) { onChange(true) }
    }
}

@Composable
private fun Filter(label: String, active: Boolean, onClick: () -> Unit) {
    Text(
        label,
        color = if (active) Color.White else Color.Black,
        modifier = Modifier
            .background(if (active) Color(0xFF1565C0) else Color(0xFFE0E0E0), RoundedCornerShape(16.dp))
            .clickable(role = Role.Button, onClick = onClick)
            .padding(horizontal = 16.dp, vertical = 12.dp),
    )
}

@Composable
private fun Messages(messages: List<Message>, modifier: Modifier = Modifier) {
    val listState = rememberLazyListState()
    LaunchedEffect(messages.size) { listState.scrollToItem(messages.lastIndex) }
    LazyColumn(modifier, state = listState, verticalArrangement = Arrangement.spacedBy(8.dp)) {
        items(messages, key = Message::id) { message ->
            Text(
                message.text,
                modifier = Modifier
                    .fillMaxWidth()
                    .background(if (message.fromUser) Color(0xFFE3F2FD) else Color(0xFFF5F5F5), RoundedCornerShape(8.dp))
                    .padding(12.dp),
            )
        }
    }
}

@Composable
private fun Options(options: List<String>, onChoose: (String) -> Unit) {
    Row(Modifier.padding(vertical = 8.dp), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
        options.forEach { option ->
            Text(
                option,
                modifier = Modifier
                    .background(Color(0xFFE0E0E0), RoundedCornerShape(16.dp))
                    .clickable(role = Role.Button) { onChoose(option) }
                    .padding(horizontal = 16.dp, vertical = 12.dp),
            )
        }
    }
}

@Composable
private fun Composer() {
    var draft by remember { mutableStateOf("") }
    Row(Modifier.padding(vertical = 8.dp), verticalAlignment = Alignment.CenterVertically) {
        TextField(
            value = draft,
            onValueChange = { draft = it },
            placeholder = { Text("Escribe un mensaje") },
            modifier = Modifier.weight(1f),
        )
        Box(
            Modifier
                .padding(start = 8.dp)
                .size(48.dp)
                .background(Color(0xFF1565C0), CircleShape)
                .clickable { draft = "" },
        )
    }
}

@Preview
@Composable
private fun SupportScreenPreview() {
    MaterialTheme { SupportScreen() }
}
