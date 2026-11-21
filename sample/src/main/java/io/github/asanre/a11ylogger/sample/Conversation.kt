package io.github.asanre.a11ylogger.sample

data class Message(val id: Int, val text: String, val fromUser: Boolean)

data class Conversation(val messages: List<Message>, val options: List<String>) {

    fun answered(option: String): Conversation = copy(
        messages = messages +
            Message(messages.size, option, fromUser = true) +
            Message(messages.size + 1, "Gracias. Un agente revisará «$option» y te escribirá hoy.", fromUser = false),
        options = emptyList(),
    )
}

private const val TERMS_PARAGRAPH =
    "Las condiciones del servicio de soporte se aplican a todas las consultas abiertas desde la aplicación. "

fun initialConversation(): Conversation = Conversation(
    messages = List(40) { index ->
        val text = when {
            index == 20 -> TERMS_PARAGRAPH.repeat(50)
            index % 2 == 0 -> "Mensaje ${index + 1}: ¿en qué podemos ayudarte con tu pedido?"
            else -> "Mensaje ${index + 1}: quiero saber cuándo llega."
        }
        Message(index, text, fromUser = index % 2 == 1)
    } + Message(40, "¿Sobre qué es tu consulta?", fromUser = false),
    options = listOf("Envío", "Devolución", "Factura"),
)
