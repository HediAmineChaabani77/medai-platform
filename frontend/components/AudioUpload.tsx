"use client";
import { useRef, useState } from "react";
import { Mic, Square, Upload, Loader2 } from "lucide-react";
import { cn } from "@/lib/cn";
import { Button } from "@/components/ui/Button";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8001";

/**
 * UC2 audio ingress: record with MediaRecorder OR upload a file,
 * POST to /api/uc2/transcribe, and hand the transcript back up.
 */
export default function AudioUpload({
  onTranscript, lang = "fr",
}: { onTranscript: (text: string) => void; lang?: string }) {
  const [recording, setRecording] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const mrRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const postAudio = async (blob: Blob, name = "audio.webm") => {
    setBusy(true); setError(null);
    try {
      const fd = new FormData();
      fd.append("audio", blob, name);
      fd.append("language", lang);
      const r = await fetch(`${API}/api/uc2/transcribe`, { method: "POST", body: fd });
      if (!r.ok) throw new Error(`status ${r.status}`);
      const { text } = await r.json();
      onTranscript(text || "");
    } catch (e: any) {
      setError(`Transcription: ${e.message}`);
    } finally {
      setBusy(false);
    }
  };

  const startRecording = async () => {
    setError(null);
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mr = new MediaRecorder(stream);
      mrRef.current = mr;
      chunksRef.current = [];
      mr.ondataavailable = (e) => { if (e.data.size > 0) chunksRef.current.push(e.data); };
      mr.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(chunksRef.current, { type: "audio/webm" });
        await postAudio(blob, "recording.webm");
      };
      mr.start();
      setRecording(true);
    } catch (e: any) {
      setError("Microphone indisponible.");
    }
  };

  const stopRecording = () => {
    mrRef.current?.stop();
    setRecording(false);
  };

  const onFile: React.ChangeEventHandler<HTMLInputElement> = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    await postAudio(file, file.name);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button
        type="button"
        variant={recording ? "accent" : "ghost"}
        onClick={recording ? stopRecording : startRecording}
        disabled={busy}
        className={cn(recording && "animate-pulseSoft")}
      >
        {recording ? <Square className="h-3.5 w-3.5" /> : <Mic className="h-3.5 w-3.5" />}
        {recording ? "Arrêter" : "Enregistrer"}
      </Button>

      <Button type="button" variant="ghost" onClick={() => fileInputRef.current?.click()} disabled={busy}>
        <Upload className="h-3.5 w-3.5" /> Importer un fichier audio
      </Button>
      <input
        ref={fileInputRef}
        type="file"
        accept="audio/*,.wav,.mp3,.m4a,.webm"
        className="hidden"
        onChange={onFile}
      />

      {busy && (
        <span className="flex items-center gap-2 text-[12px] text-muted">
          <Loader2 className="h-3.5 w-3.5 animate-spin" />
          Transcription locale (Whisper)...
        </span>
      )}
      {error && <span className="text-[12px] text-danger">{error}</span>}
    </div>
  );
}
