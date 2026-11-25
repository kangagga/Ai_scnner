package com.aiscanner.app.ui.screens.settings

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.aiscanner.app.AIScannerApp
import com.aiscanner.app.data.api.NetworkModule
import com.aiscanner.app.ui.components.StatusBanner
import com.aiscanner.app.ui.theme.GreenPrimary
import com.aiscanner.app.ui.theme.TextPrimary
import com.aiscanner.app.ui.theme.TextSecondary

@Composable
fun SettingsScreen() {
    val context = LocalContext.current
    val app = context.applicationContext as AIScannerApp
    var url by rememberSaveable { mutableStateOf(NetworkModule.baseUrl) }
    var saved by remember { mutableStateOf(false) }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(16.dp)
    ) {
        Text(
            text = "Pengaturan Koneksi",
            style = MaterialTheme.typography.headlineSmall,
            color = TextPrimary,
            fontWeight = FontWeight.Bold
        )
        Text(
            text = "Atur alamat server bot (URL API).",
            style = MaterialTheme.typography.bodyMedium,
            color = TextSecondary
        )
        Spacer(Modifier.height(16.dp))

        OutlinedTextField(
            value = url,
            onValueChange = {
                url = it
                saved = false
            },
            label = { Text("Base URL") },
            supportingText = {
                Text("Contoh: http://192.168.1.10:5000/")
            },
            singleLine = true,
            modifier = Modifier.fillMaxWidth()
        )

        Spacer(Modifier.height(16.dp))

        Button(
            onClick = {
                app.saveBaseUrl(url)
                saved = true
            },
            modifier = Modifier.fillMaxWidth(),
            colors = ButtonDefaults.buttonColors(containerColor = GreenPrimary)
        ) {
            Text("Simpan & Terapkan", fontWeight = FontWeight.SemiBold)
        }

        if (saved) {
            Spacer(Modifier.height(16.dp))
            StatusBanner(text = "Base URL tersimpan. Buka kembali menu untuk memuat data.", color = GreenPrimary)
        }

        Spacer(Modifier.height(24.dp))
        Text(
            text = "Catatan keamanan",
            style = MaterialTheme.typography.titleMedium,
            color = TextPrimary
        )
        Spacer(Modifier.height(8.dp))
        Text(
            text = "• Aplikasi berjalan dalam mode PAPER TRADING.\n" +
                "• Tidak ada tombol live order.\n" +
                "• API Control Key tidak disimpan di aplikasi; dimasukkan manual saat akan mengirim perintah kontrol.\n" +
                "• Semua data ditampilkan berasal dari API bot yang asli.",
            style = MaterialTheme.typography.bodySmall,
            color = TextSecondary
        )

        Spacer(Modifier.height(12.dp))
        Row(
            modifier = Modifier.fillMaxWidth(),
            horizontalArrangement = Arrangement.Start
        ) {
            Text(
                text = "Status: ",
                style = MaterialTheme.typography.bodySmall,
                color = TextSecondary
            )
            Text(
                text = if (NetworkModule.baseUrl.startsWith("http")) "Terhubung ke ${NetworkModule.baseUrl}" else "Belum dikonfigurasi",
                style = MaterialTheme.typography.bodySmall,
                color = TextPrimary
            )
        }
    }
}
