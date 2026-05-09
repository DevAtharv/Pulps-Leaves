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

const testimonials = [
  {
    name: "Priya Mehta",
    location: "Mumbai",
    text: "The makhana is on a completely different level. I can taste the difference immediately — light, fresh, nothing like the supermarket stuff.",
    tag: "Makhana · From Bihar",
    tagColor: "text-[#E8A020]",
  },
  {
    name: "Arjun Das",
    location: "Bengaluru",
    text: "Ordered the Assam tea on a whim. Now I'm three orders deep. The first flush is extraordinary — complex, brisk, incredibly fresh.",
    tag: "Assam Tea · First Flush",
    tagColor: "text-teal-400",
  },
  {
    name: "Sunita Rao",
    location: "Pune",
    text: "Got the Malda mangoes for my family. They couldn't believe it wasn't from a local orchard. The sweetness is insane — zero sourness.",
    tag: "Malda Mangoes · From Bihar",
    tagColor: "text-[#E8A020]",
  },
]

export default function Testimonials() {
  const ref = useRef(null)
  const isInView = useInView(ref, { once: true, margin: "-80px" })

  return (
    <section className="bg-[#0d1f0e] py-24 px-6 md:px-10 border-t border-white/5">
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
            WHAT PEOPLE SAY
          </span>
          <h2 className="text-3xl md:text-5xl font-medium text-white mt-3 tracking-tight">
            Taste speaks for itself.
          </h2>
        </motion.div>

        {/* Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          {testimonials.map((t, i) => (
            <motion.div
              key={i}
              variants={fadeUp}
              className="p-6 rounded-2xl bg-white/[0.03] border border-white/8 flex flex-col gap-4"
            >
              <p className="text-white/70 text-sm leading-relaxed flex-1">
                &ldquo;{t.text}&rdquo;
              </p>
              <div>
                <div className="text-white font-medium text-sm">{t.name}</div>
                <div className="text-white/35 text-xs">{t.location}</div>
                <div className={`text-[10px] mt-2 font-medium tracking-wide ${t.tagColor}`}>
                  {t.tag}
                </div>
              </div>
            </motion.div>
          ))}
        </div>
      </motion.div>
    </section>
  )
}
