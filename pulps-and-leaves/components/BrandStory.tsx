"use client"

import { useRef } from "react"
import { motion, useInView, Variants } from "motion/react"

const fadeUp: Variants = {
  hidden: { opacity: 0, y: 40 },
  visible: {
    opacity: 1,
    y: 0,
    transition: { duration: 0.6, ease: [0.22, 1, 0.36, 1] },
  },
}

export default function BrandStory() {
  const ref = useRef(null)
  const isInView = useInView(ref, { once: true, margin: "-80px" })

  return (
    <section id="story" className="bg-[#0a1a0b] py-24 px-6 md:px-10 border-t border-white/5">
      <motion.div
        ref={ref}
        variants={fadeUp}
        initial="hidden"
        animate={isInView ? "visible" : "hidden"}
        className="max-w-5xl mx-auto grid grid-cols-1 md:grid-cols-2 gap-12 md:gap-20 items-center"
      >
        {/* Image column */}
        <div className="relative rounded-2xl overflow-hidden h-80 md:h-[440px]">
          <img
            src="https://images.unsplash.com/photo-1556909114-f6e7ad7d3136?w=800&auto=format&fit=crop"
            alt="Tea garden aerial view — origin of Pulps & Leaves"
            className="w-full h-full object-cover"
            loading="lazy"
          />
          {/* Subtle dark vignette */}
          <div className="absolute inset-0 bg-gradient-to-br from-transparent via-transparent to-black/40" />
          <div className="absolute bottom-4 left-4">
            <span className="text-[10px] tracking-[0.18em] text-teal-400 bg-teal-400/10 border border-teal-400/30 px-3 py-1 rounded-full font-medium">
              From Assam
            </span>
          </div>
        </div>

        {/* Text column */}
        <div className="flex flex-col gap-6">
          <span className="text-[10px] tracking-[0.25em] text-[#E8A020]/70 font-medium">
            OUR STORY
          </span>
          <h2 className="text-3xl md:text-4xl font-medium text-white tracking-tight leading-snug">
            Born in a Bihar kitchen.<br />
            <span className="text-[#E8A020]">Built for India's pantry.</span>
          </h2>
          <p className="text-white/55 text-sm md:text-base leading-relaxed">
            Pulps &amp; Leaves started when our founder couldn&apos;t find real makhana in the city — 
            the kind his grandmother used to make. What he found in supermarkets was 
            bleached, stale, and travelled 3,000 km through four middlemen.
          </p>
          <p className="text-white/55 text-sm md:text-base leading-relaxed">
            So he went to Mithila himself. Then to Assam&apos;s tea estates. Then to Malda&apos;s 
            mango orchards. Each product now comes with a farm ID — you can trace exactly 
            where your food was grown.
          </p>
          <div className="flex gap-8 pt-2">
            {[
              { value: "2021", label: "Founded" },
              { value: "120+", label: "Farm partners" },
              { value: "3", label: "States sourced" },
            ].map((stat) => (
              <div key={stat.label}>
                <div className="text-xl font-medium text-[#E8A020]">{stat.value}</div>
                <div className="text-white/40 text-xs mt-0.5">{stat.label}</div>
              </div>
            ))}
          </div>
        </div>
      </motion.div>
    </section>
  )
}
