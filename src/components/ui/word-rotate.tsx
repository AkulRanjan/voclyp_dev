"use client";

import React from "react";
import { AnimatePresence, HTMLMotionProps, motion } from "motion/react";

import { cn } from "@/lib/utils";

/**
 * Props for the WordRotate component
 */
export interface WordRotateProps {
  /**
   * Array of words to rotate through
   */
  words: string[];
  /**
   * Duration in milliseconds for each word display before rotating to the next
   * @default 2000
   */
  duration?: number;
}

export function WordRotate({
  words,
  className,
  duration = 2000,
}: HTMLMotionProps<"div"> & WordRotateProps) {
  const [index, setIndex] = React.useState(0);

  React.useEffect(() => {
    const timeoutId = setTimeout(() => {
      if (index === words.length - 1) {
        setIndex(0);
      } else {
        setIndex(index + 1);
      }
    }, duration);
    return () => clearTimeout(timeoutId);
  }, [index, words, duration]);

  return (
    <span className="relative inline-flex items-center justify-center overflow-hidden py-1 align-bottom">
      <AnimatePresence mode="popLayout" initial={false}>
        <motion.span
          key={words[index]}
          initial={{ opacity: 0, y: "0.5em", filter: "blur(4px)" }}
          animate={{ opacity: 1, y: "0em", filter: "blur(0px)" }}
          exit={{ opacity: 0, y: "-0.5em", filter: "blur(4px)" }}
          transition={{
            y: { type: "spring", stiffness: 140, damping: 20, mass: 0.8 },
            opacity: { duration: 0.35, ease: "easeOut" },
            filter: { duration: 0.35, ease: "easeOut" },
          }}
          className={cn("inline-block", className)}
        >
          {words[index]}
        </motion.span>
      </AnimatePresence>
    </span>
  );
}
