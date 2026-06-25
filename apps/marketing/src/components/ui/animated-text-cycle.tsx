"use client";

import { useEffect, useMemo, useState } from "react";
import { AnimatePresence, motion, type Variants } from "framer-motion";

interface AnimatedTextCycleProps {
  words: string[];
  interval?: number;
  className?: string;
}

const variants: Variants = {
  hidden: { y: "-0.5em", opacity: 0, filter: "blur(6px)" },
  visible: {
    y: 0,
    opacity: 1,
    filter: "blur(0px)",
    transition: { duration: 0.4, ease: "easeOut" },
  },
  exit: {
    y: "0.5em",
    opacity: 0,
    filter: "blur(6px)",
    transition: { duration: 0.3, ease: "easeIn" },
  },
};

export default function AnimatedTextCycle({
  words,
  interval = 5000,
  className = "",
}: AnimatedTextCycleProps) {
  const [index, setIndex] = useState(0);
  const longest = useMemo(
    () => words.reduce((a, b) => (a.length >= b.length ? a : b), ""),
    [words],
  );

  useEffect(() => {
    const timer = setInterval(() => {
      setIndex((prev) => (prev + 1) % words.length);
    }, interval);
    return () => clearInterval(timer);
  }, [interval, words.length]);

  return (
    <span className="inline-grid shrink-0 align-baseline text-left leading-[inherit]">
      <span
        aria-hidden
        className={`invisible col-start-1 row-start-1 whitespace-nowrap ${className}`}
      >
        {longest}
      </span>

      <span className="col-start-1 row-start-1 overflow-hidden text-left">
        <AnimatePresence mode="wait" initial={false}>
          <motion.span
            key={index}
            className={`inline-block whitespace-nowrap text-left ${className}`}
            variants={variants}
            initial="hidden"
            animate="visible"
            exit="exit"
          >
            {words[index]}
          </motion.span>
        </AnimatePresence>
      </span>
    </span>
  );
}
