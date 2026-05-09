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

const staggerParent: Variants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.1 } },
}

const features = [
  {
    icon: "🌿",
    title: "Zero Chemicals",
    desc: "Every product is grown without synthetic fertilisers or pesticides. Tested before it reaches you.",
  },
  {
    icon: "🚜",
    title: "Farm-Direct Sourcing",
    desc: "We work directly with small-hold farmers in Bihar and Assam — no middlemen, fair prices.",
  },
  {
    icon: "📦",
    title: "Freshness Guaranteed",
    desc: "Shipped within 24–48 hours of harvest. Cold-chain from farm to your doorstep.",
  },
  {
    icon: "🤝",
    title: "Farmer-First Model",
    desc: "30% of every sale goes back to the farming family. We track every purchase to the source.",
  },
]

export default function WhyChooseUs() {
  const ref = useRef(null)
  const isInView = useInView(ref, { once: true, margin: "-80px" })

  return (
    <section className="bg-[#0d1f0e] py-24 px-6 md:px-10">
      <motion.div
        ref={ref}
        variants={staggerParent}
        initial="hidden"
        animate={isInView ? "visible" : "hidden"}
        className="max-w-5xl mx-auto"
      >
        {/* Header */}
        <motion.div variants={fadeUp} className="mb-14 text-center">
          <span className="text-[10px] tracking-[0.25em] text-[#E8A020]/70 font-medium">
            WHY CHOOSE US
          </span>
          <h2 className="text-3xl md:text-5xl font-medium text-white mt-3 tracking-tight">
            The difference is in the detail.
          </h2>
        </motion.div>

        {/* Cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {features.map((feature, i) => (
            <motion.div
              key={i}
              variants={fadeUp}
              className="flex gap-4 p-6 rounded-2xl border border-white/8 bg-white/[0.03] group hover:border-[#E8A020]/25 transition-colors duration-300"
            >
              <div className="text-2xl flex-shrink-0">{feature.icon}</div>
              <div>
                <h3 className="text-white font-medium text-base mb-2">{feature.title}</h3>
                <p className="text-white/50 text-sm leading-relaxed">{feature.desc}</p>
              </div>
            </motion.div>
          ))}
        </div>
      </motion.div>
    </section>
  )
}
