import { cva, type VariantProps } from "class-variance-authority";
import { forwardRef, type ButtonHTMLAttributes } from "react";
import { cn } from "@/lib/cn";

const button = cva(
  "btn disabled:opacity-50 disabled:cursor-not-allowed select-none",
  {
    variants: {
      variant: {
        primary: "btn-primary",
        ghost: "btn-ghost",
        accent: "btn-accent",
        danger: "bg-danger text-white border border-danger hover:opacity-90",
      },
      size: {
        sm: "px-3 py-1.5 text-xs",
        md: "px-3.5 py-2 text-[13px]",
        lg: "px-4 py-2.5 text-sm",
      },
    },
    defaultVariants: { variant: "primary", size: "md" },
  }
);

export interface ButtonProps
  extends ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof button> {}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, ...props }, ref) => (
    <button ref={ref} className={cn(button({ variant, size }), className)} {...props} />
  )
);
Button.displayName = "Button";
