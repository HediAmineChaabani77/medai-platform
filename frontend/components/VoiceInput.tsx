"use client";
import { useEffect, useRef, useState } from "react";
import { Mic, Square } from "lucide-react";
import { cn } from "@/lib/cn";

/**
 * Browser-native dictation using the Web Speech API. Falls back silently if
 * the browser does not support it (Firefox, Safari on iOS < 14.5). Language
 * defaults to fr-FR.
 */
export default function VoiceInput({
  onTranscript, lang = "fr-FR", className,
}: {
  onTranscript: (text: string) => void;
  lang?: string;
  className?: string;
}) {
  const [supported, setSupported] = useState(false);
  const [listening, setListening] = useState(false);
  const recRef = useRef<any>(null);

  useEffect(() => {
    const w = window as any;
    const SR = w.SpeechRecognition || w.webkitSpeechRecognition;
    if (!SR) return;
    setSupported(true);
    const r = new SR();
    r.lang = lang;
    r.continuous = true;
    r.interimResults = true;
    r.onresult = (e: any) => {
      let text = "";
      for (let i = 0; i < e.results.length; i++) {
        text += e.results[i][0].transcript;
      }
      onTranscript(text.trim());
    };
    r.onend = () => setListening(false);
    recRef.current = r;
  }, [lang, onTranscript]);

  if (!supported) return null;

  const toggle = () => {
    if (!recRef.current) return;
    if (listening) { recRef.current.stop(); setListening(false); }
    else { recRef.current.start(); setListening(true); }
  };

  return (
    <button
      type="button"
      onClick={toggle}
      className={cn(
        "btn",
        listening ? "btn-accent animate-pulseSoft" : "btn-ghost",
        className
      )}
      aria-pressed={listening}
      aria-label={listening ? "Arrêter la dictée" : "Commencer la dictée vocale"}
    >
      {listening ? <Square className="h-3.5 w-3.5" /> : <Mic className="h-3.5 w-3.5" />}
      {listening ? "Arrêter" : "Dictée vocale"}
    </button>
  );
}
