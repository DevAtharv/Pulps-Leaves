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

const collections = [
  {
    tag: "From Bihar",
    tagColor: "text-[#E8A020] bg-[#E8A020]/10 border-[#E8A020]/30",
    identity: "amber",
    name: "Mithila Makhana",
    subtitle: "Water lily seeds, hand-harvested",
    desc: "Grown in the pristine wetlands of Mithila, our makhana is sun-dried and naturally processed — zero chemicals, zero preservatives.",
    image: "https://images.unsplash.com/photo-1504674900247-0877df9cc836?w=700&auto=format&fit=crop",
    accent: "#E8A020",
    accentBg: "#142816",
  },
  {
    tag: "From Assam",
    tagColor: "text-teal-400 bg-teal-400/10 border-teal-400/30",
    identity: "teal",
    name: "Brahmaputra Valley Tea",
    subtitle: "First-flush Assam CTC & orthodox",
    desc: "Handpicked from small gardens along the Brahmaputra floodplains. Rich, malty, and naturally caffeine-forward.",
    image: "https://images.unsplash.com/photo-1576092768241-dec231879fc3?w=700&auto=format&fit=crop",
    accent: "#14b8a6",
    accentBg: "#0a1e1e",
  },
  {
    tag: "From Bihar",
    tagColor: "text-[#E8A020] bg-[#E8A020]/10 border-[#E8A020]/30",
    identity: "amber",
    name: "Malda Alphonso Mangoes",
    subtitle: "Seasonal · Limited harvest",
    desc: "The king of mangoes from the orchards of Malda. Pure, unadulterated sweetness — no ripening agents, no wax coating.",
    image: "https://images.unsplash.com/photo-1553279768-865429fa0078?w=700&auto=format&fit=crop",
    accent: "#E8A020",
    accentBg: "#142816",
  },
]

export default function OriginCollections() {
  const ref = useRef(null)
  const isInView = useInView(ref, { once: true, margin: "-80px" })

  return (
    <section id="shop" className="bg-[#0d1f0e] py-24 px-6 md:px-10">
      <motion.div
        ref={ref}
        variants={staggerParent}
        initial="hidden"
        animate={isInView ? "visible" : "hidden"}
        className="max-w-6xl mx-auto"
      >
        {/* Header */}
        <motion.div variants={fadeUp} className="mb-14 text-center">
          <span className="text-[10px] tracking-[0.25em] text-[#E8A020]/70 font-medium">
            ORIGIN COLLECTIONS
          </span>
          <h2 className="text-3xl md:text-5xl font-medium text-white mt-3 tracking-tight">
            Straight from the source.
          </h2>
          <p className="text-white/50 mt-4 max-w-lg mx-auto text-sm md:text-base leading-relaxed">
            Every product traces back to a specific region, a specific farmer — nothing in between.
          </p>
        </motion.div>

        {/* Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          {collections.map((col, i) => (
            <motion.div
              key={i}
              variants={fadeUp}
              className="rounded-2xl overflow-hidden flex flex-col"
              style={{ background: col.accentBg }}
            >
              {/* Image */}
              <div className="relative h-52 overflow-hidden">
                <img
                  src={col.image}
                  alt={col.name}
                  className="w-full h-full object-cover"
                  loading="lazy"
                />
                <div className="absolute inset-0" style={{ background: "linear-gradient(to top, rgba(0,0,0,0.5) 0%, transparent 60%)" }} />
              </div>
              {/* Content */}
              <div className="p-5 flex flex-col gap-3 flex-1">
                <span className={`text-[10px] tracking-[0.18em] font-medium border px-3 py-1 rounded-full self-start ${col.tagColor}`}>
                  {col.tag}
                </span>
                <div>
                  <h3 className="text-white font-medium text-lg leading-snug">{col.name}</h3>
                  <p className="text-white/40 text-xs mt-0.5">{col.subtitle}</p>
                </div>
                <p className="text-white/60 text-sm leading-relaxed flex-1">{col.desc}</p>
                <motion.button
                  className="mt-2 text-xs sm:text-sm font-medium rounded-full px-4 py-2 sm:px-5 sm:py-2.5 self-start"
                  style={{ background: col.accent, color: "#0d1f0e" }}
                  whileHover={{ scale: 1.04 }}
                  whileTap={{ scale: 0.97 }}
                  transition={{ type: "spring", stiffness: 400, damping: 28 }}
                >
                  Shop {col.name.split(" ")[0]}
                </motion.button>
              </div>
            </motion.div>
          ))}
        </div>
      </motion.div>
    </section>
  )
}
