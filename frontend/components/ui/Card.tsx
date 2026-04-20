import { forwardRef, type HTMLAttributes } from "react";
import { cn } from "@/lib/cn";

export const Card = forwardRef<HTMLDivElement, HTMLAttributes<HTMLDivElement>>(
  ({ className, ...p }, ref) => (
    <div ref={ref} className={cn("surface", className)} {...p} />
  )
);
Card.displayName = "Card";

export const CardHeader = ({ className, ...p }: HTMLAttributes<HTMLDivElement>) => (
  <div className={cn("px-5 py-4 rule", className)} {...p} />
);
export const CardBody = ({ className, ...p }: HTMLAttributes<HTMLDivElement>) => (
  <div className={cn("px-5 py-4", className)} {...p} />
);
export const CardFooter = ({ className, ...p }: HTMLAttributes<HTMLDivElement>) => (
  <div className={cn("px-5 py-3 rule border-t border-b-0", className)} {...p} />
);
