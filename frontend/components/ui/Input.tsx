import { cloneElement, forwardRef, useId, type InputHTMLAttributes, type TextareaHTMLAttributes } from "react";
import { cn } from "@/lib/cn";

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...p }, ref) => (
    <input ref={ref} className={cn("input", className)} {...p} />
  )
);
Input.displayName = "Input";

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaHTMLAttributes<HTMLTextAreaElement>>(
  ({ className, rows = 5, ...p }, ref) => (
    <textarea
      ref={ref}
      rows={rows}
      className={cn("input min-h-[120px] resize-y leading-relaxed", className)}
      {...p}
    />
  )
);
Textarea.displayName = "Textarea";

export const Label = ({ children, htmlFor }: { children: React.ReactNode; htmlFor?: string }) => (
  <label className="label" htmlFor={htmlFor}>{children}</label>
);

/**
 * Field wires a label → control via auto-generated id, so every control has an
 * associated label even when callers don't pass an explicit id. Accepts a
 * single React element (Input/Textarea/select) as children and injects `id`.
 */
export function Field({
  label, hint, children, id,
}: {
  label: string;
  hint?: string;
  children: React.ReactElement;
  id?: string;
}) {
  const auto = useId();
  const controlId = id ?? (children.props as { id?: string })?.id ?? `fld-${auto}`;
  const child = cloneElement(children, { id: controlId } as any);
  return (
    <div>
      <div className="flex items-baseline justify-between">
        <Label htmlFor={controlId}>{label}</Label>
        {hint && <span className="text-[11px] text-subtle">{hint}</span>}
      </div>
      {child}
    </div>
  );
}
