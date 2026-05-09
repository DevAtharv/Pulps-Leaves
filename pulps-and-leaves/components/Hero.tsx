"use client"

import { useEffect, useRef } from "react"
import { LayoutGroup, motion } from "motion/react"
import Floating, { FloatingElement } from "@/components/ui/parallax-floating"
import { TextRotate } from "@/components/ui/text-rotate"

const COLS = 8
const ROWS = 6
const TILE_COUNT = COLS * ROWS
const shades = [
  "#0d1f0e","#102212","#122514","#142816",
  "#162b18","#182e1a","#1a321c","#1c351e",
]

const images = [
  {
    url: "https://images.unsplash.com/photo-1556909114-f6e7ad7d3136?w=600&auto=format&fit=crop",
    alt: "Lush green tea garden rows aerial view",
    depth: 0.5,
    delay: 0.5,
    position: "top-[15%] left-[2%] md:top-[20%] md:left-[5%]",
    className: "w-24 h-16 md:w-32 md:h-24 object-cover rounded-xl -rotate-[3deg] shadow-2xl hover:scale-105 transition-transform",
  },
  {
    url: "https://images.unsplash.com/photo-1601493700631-2b16ec4b4716?w=600&auto=format&fit=crop",
    alt: "Close-up of ripe mango on tree",
    depth: 1,
    delay: 0.7,
    position: "top-[0%] left-[8%] md:top-[5%] md:left-[10%]",
    className: "w-40 h-28 md:w-56 md:h-44 object-cover rounded-xl -rotate-12 shadow-2xl hover:scale-105 transition-transform",
  },
  {
    url: "https://images.unsplash.com/photo-1504674900247-0877df9cc836?w=600&auto=format&fit=crop",
    alt: "Bihar farmer harvesting makhana in pond",
    depth: 4,
    delay: 0.9,
    position: "top-[80%] left-[5%] md:top-[72%] md:left-[7%]",
    className: "w-40 h-40 md:w-60 md:h-60 object-cover rounded-xl -rotate-[4deg] shadow-2xl hover:scale-105 transition-transform",
  },
  {
    url: "https://images.unsplash.com/photo-1576092768241-dec231879fc3?w=600&auto=format&fit=crop",
    alt: "Assam tea leaves being hand-picked",
    depth: 2,
    delay: 1.1,
    position: "top-[0%] left-[85%] md:top-[3%] md:left-[82%]",
    className: "w-40 h-36 md:w-60 md:h-52 object-cover rounded-xl rotate-[6deg] shadow-2xl hover:scale-105 transition-transform",
  },
  {
    url: "https://images.unsplash.com/photo-1553279768-865429fa0078?w=600&auto=format&fit=crop",
    alt: "Sliced Malda mangoes on wooden surface",
    depth: 1,
    delay: 1.3,
    position: "top-[72%] left-[82%] md:top-[65%] md:left-[82%]",
    className: "w-44 h-44 md:w-72 md:h-72 object-cover rounded-xl rotate-[19deg] shadow-2xl hover:scale-105 transition-transform",
  },
]

export default function Hero() {
  const tilesRef = useRef<HTMLDivElement[]>([])

  useEffect(() => {
    const tiles = tilesRef.current
    tiles.forEach((tile) => {
      if (!tile) return
      const delay = Math.random() * 0.7
      const shade = shades[Math.floor(Math.random() * shades.length)]
      tile.style.background = shade
      tile.style.transition = `opacity 0.5s cubic-bezier(0.34,1.56,0.64,1) ${delay}s, transform 0.5s cubic-bezier(0.34,1.56,0.64,1) ${delay}s`
      requestAnimationFrame(() => {
        tile.style.opacity = "1"
        tile.style.transform = "scale(1)"
      })
    })
  }, [])

  return (
    <section
      id="hero"
      className="w-full h-screen overflow-hidden flex flex-col items-center justify-center relative bg-[#0d1f0e]"
    >
      {/* TILE GRID (z-0) */}
      <div
        className="absolute inset-0 z-0"
        style={{
          display: "grid",
          gridTemplateColumns: `repeat(${COLS}, 1fr)`,
          gridTemplateRows: `repeat(${ROWS}, 1fr)`,
        }}
      >
        {Array.from({ length: TILE_COUNT }).map((_, i) => (
          <div
            key={i}
            ref={(el) => { if (el) tilesRef.current[i] = el }}
            className="w-full h-full transition-colors duration-300"
            style={{
              opacity: 0,
              transform: "scale(0.85)",
              background: "#0d1f0e",
            }}
            onMouseEnter={(e) => {
              (e.currentTarget as HTMLDivElement).style.background = "rgba(232,160,32,0.15)"
            }}
            onMouseLeave={(e) => {
              const shade = shades[Math.floor(Math.random() * shades.length)]
              ;(e.currentTarget as HTMLDivElement).style.background = shade
            }}
          />
        ))}
      </div>

      {/* RADIAL GRADIENT OVERLAY (z-1) */}
      <div
        className="absolute inset-0 z-[1] pointer-events-none"
        style={{
          background:
            "radial-gradient(ellipse at 30% 50%, rgba(13,31,14,0.92) 0%, rgba(13,31,14,0.6) 60%, transparent 100%)",
        }}
      />

      {/* FLOATING IMAGES (z-10) */}
      <div className="absolute inset-0 z-10 pointer-events-none">
        <Floating sensitivity={-0.5} className="h-full">
          {images.map((img, i) => (
            <FloatingElement key={i} depth={img.depth} className={img.position}>
              <motion.img
                src={img.url}
                alt={img.alt}
                className={img.className}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 0.8, delay: img.delay }}
                loading="lazy"
              />
            </FloatingElement>
          ))}
        </Floating>
      </div>

      {/* HERO CENTER CONTENT (z-50) */}
      <div className="flex flex-col items-center justify-center w-[90%] sm:w-[360px] md:w-[520px] lg:w-[700px] z-50">

        {/* Eyebrow Pill */}
        <motion.span
          className="text-[10px] tracking-[0.2em] font-medium border border-[#E8A020]/40 text-[#E8A020] bg-[#E8A020]/10 px-4 py-1.5 rounded-full mb-6"
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.3, ease: [0.22, 1, 0.36, 1] }}
        >
          DIRECT FROM FARM · INDIA
        </motion.span>

        {/* Headline */}
        <h1 className="text-4xl sm:text-5xl md:text-7xl lg:text-8xl text-center font-semibold tracking-tight text-white leading-tight space-y-2 flex flex-col items-center">
          <motion.span
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.4, ease: [0.22, 1, 0.36, 1] }}
          >
            Pure. Regional.
          </motion.span>
          <motion.span
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 0.5, ease: [0.22, 1, 0.36, 1] }}
          >
            <LayoutGroup>
              <motion.span layout className="flex flex-wrap justify-center">
                <TextRotate
                  texts={[
                    "Makhana.",
                    "Assam Tea.",
                    "Malda Mangoes.",
                    "Farm Fresh.",
                    "From Bihar.",
                    "From Assam.",
                    "No Chemicals.",
                    "Straight to You.",
                  ]}
                  mainClassName="text-[#E8A020] overflow-hidden px-3 pb-2 md:pb-3 rounded-xl"
                  staggerDuration={0.04}
                  staggerFrom="last"
                  rotationInterval={2800}
                  transition={{ type: "spring", damping: 28, stiffness: 380 }}
                />
              </motion.span>
            </LayoutGroup>
          </motion.span>
        </h1>

        {/* Subtext */}
        <motion.p
          className="text-sm sm:text-base md:text-lg text-center text-white/65 pt-6 md:pt-8 max-w-md leading-relaxed"
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.6, delay: 0.55, ease: [0.22, 1, 0.36, 1] }}
        >
          Authentic Assam tea, Bihar&apos;s finest makhana, and seasonal Malda mangoes
          — sourced directly from farms.
        </motion.p>

        {/* Location Pills */}
        <motion.div
          className="flex gap-2 flex-wrap justify-center pt-4"
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.65, ease: [0.22, 1, 0.36, 1] }}
        >
          {["📍 Malda, Bihar", "📍 Mithila, Bihar", "📍 Brahmaputra, Assam"].map((pill) => (
            <span
              key={pill}
              className="text-[11px] bg-white/10 border border-white/20 text-white/80 px-3 py-1 rounded-full"
            >
              {pill}
            </span>
          ))}
        </motion.div>

        {/* CTA Buttons */}
        <motion.div
          className="flex gap-3 mt-8 md:mt-10"
          initial={{ opacity: 0, y: 12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.5, delay: 0.75, ease: [0.22, 1, 0.36, 1] }}
        >
          <motion.button
            id="shop-now-btn"
            className="text-sm md:text-base font-medium text-white bg-[#E8A020] px-6 py-3 md:px-8 md:py-3.5 rounded-full shadow-lg z-20"
            whileHover={{
              scale: 1.04,
              boxShadow: "0 0 24px rgba(232,160,32,0.4)",
            }}
            whileTap={{ scale: 0.97 }}
            transition={{ type: "spring", stiffness: 400, damping: 28 }}
          >
            Shop Now
          </motion.button>
          <motion.button
            id="explore-origins-btn"
            className="text-sm md:text-base font-medium text-white border border-white/40 bg-white/5 px-6 py-3 md:px-8 md:py-3.5 rounded-full z-20"
            whileHover={{ scale: 1.04, borderColor: "rgba(255,255,255,0.7)" }}
            whileTap={{ scale: 0.97 }}
            transition={{ type: "spring", stiffness: 400, damping: 28 }}
          >
            Explore Origins
          </motion.button>
        </motion.div>
      </div>

      {/* Scroll Indicator */}
      <motion.div
        className="absolute bottom-8 left-1/2 -translate-x-1/2 flex flex-col items-center gap-1.5"
        initial={{ opacity: 0 }}
        animate={{ opacity: [1, 0.3, 1] }}
        transition={{ duration: 2, delay: 1.0, repeat: Infinity, ease: "easeInOut" }}
      >
        <div className="w-1.5 h-1.5 rounded-full bg-white/30" />
        <div className="w-px h-7 bg-white/30" />
      </motion.div>
    </section>
  )
}
