"use client"

import Navbar from "@/components/Navbar"
import Hero from "@/components/Hero"
import OriginCollections from "@/components/OriginCollections"
import MangoBanner from "@/components/MangoBanner"
import WhyChooseUs from "@/components/WhyChooseUs"
import BrandStory from "@/components/BrandStory"
import Testimonials from "@/components/Testimonials"
import Footer from "@/components/Footer"

export default function Page() {
  return (
    <main>
      <Navbar />
      <Hero />
      <OriginCollections />
      <MangoBanner />
      <WhyChooseUs />
      <BrandStory />
      <Testimonials />
      <Footer />
    </main>
  )
}
