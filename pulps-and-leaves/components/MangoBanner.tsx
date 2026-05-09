"use client"

import { useRef, useEffect, useState } from "react"
import { motion, useInView, Variants } from "motion/react"

const fadeUp: Variants = {
  hidden: { opacity: 0, y: 40 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.6, ease: [0.22, 1, 0.36, 1] },
  },
}

function useCountUp(target: number, isActive: boolean, duration = 1800) {
  const [count, setCount] = useState(0)
  useEffect(() => {
    if (!isActive) return
    let start = 0
    const step = target / (duration / 16)
    const timer = setInterval(() => {
      start += step
      if (start >= target) {
        setCount(target)
        clearInterval(timer)
      } else {
        setCount(Math.floor(start))
      }
    }, 16)
    return () => clearInterval(timer)
  }, [isActive, target, duration])
  return count
}

export default function MangoBanner() {
  const ref = useRef(null)
  const isInView = useInView(ref, { once: true, margin: "-80px" })

  const harvested = useCountUp(2400, isInView)
  const farms = useCountUp(38, isInView)
  const days = useCountUp(14, isInView)

  return (
    <section
      id="mango-urgency"
      ref={ref}
      className="bg-[#1a1200] border-y border-[#E8A020]/20 py-16 px-6 md:px-10 overflow-hidden"
    >
      <motion.div
        variants={fadeUp}
        initial="hidden"
        animate={isInView ? "visible" : "hidden"}
        className="max-w-5xl mx-auto flex flex-col md:flex-row items-center gap-10 md:gap-16"
      >
        {/* Left: urgency text */}
        <div className="flex-1 text-center md:text-left">
          <span className="text-[10px] tracking-[0.25em] text-[#E8A020]/60 font-medium">
            🥭 MANGO SEASON · LIMITED HARVEST
          </span>
          <h2 className="text-2xl md:text-4xl font-medium text-white mt-3 tracking-tight leading-snug">
            Malda&apos;s finest mangoes.<br />
            <span className="text-[#E8A020]">Direct to your door.</span>
          </h2>
          <p className="text-white/50 text-sm mt-4 max-w-sm leading-relaxed">
            No ripening agents, no wax. Harvested at peak ripeness and shipped within 24 hours. Season closes when the orchard does.
          </p>
          <motion.button
            className="mt-6 text-sm font-medium text-[#0d1f0e] bg-[#E8A020] px-7 py-3 rounded-full"
            whileHover={{ scale: 1.04, boxShadow: "0 0 24px rgba(232,160,32,0.4)" }}
            whileTap={{ scale: 0.97 }}
            transition={{ type: "spring", stiffness: 400, damping: 28 }}
          >
            Reserve Your Box →
          </motion.button>
        </div>

        {/* Right: countUp stats */}
        <div className="flex flex-wrap justify-center gap-x-6 gap-y-8 md:gap-12 mt-8 md:mt-0">
          {[
            { value: harvested, suffix: "kg", label: "Harvested this season" },
            { value: farms, suffix: "+", label: "Partner orchards" },
            { value: days, suffix: " days", label: "Left in season" },
          ].map((stat, i) => (
            <div key={i} className="text-center">
              <span className="text-3xl md:text-5xl font-medium text-[#E8A020] tabular-nums">
                {stat.value}{stat.suffix}
              </span>
              <p className="text-white/40 text-xs mt-1.5 leading-tight max-w-[80px]">
                {stat.label}
              </p>
            </div>
          ))}
        </div>
      </motion.div>
    </section>
  )
}
