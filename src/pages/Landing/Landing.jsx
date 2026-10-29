import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../../hooks/useAuth';
import {
  Milk,
  ShieldCheck,
  Award,
  Truck,
  Phone,
  Mail,
  MapPin,
  Clock,
  ArrowRight,
  Send,
  HeartHandshake,
  CheckCircle,
  ThermometerSnowflake,
  ExternalLink,
} from 'lucide-react';
import { toast } from 'react-toastify';

export function Landing() {
  const { isAuthenticated, user } = useAuth();
  const [inquirySubmitted, setInquirySubmitted] = useState(false);
  const [formData, setFormData] = useState({
    name: '',
    phone: '',
    email: '',
    product: 'Farm Fresh Buffalo Milk',
    message: '',
  });

  const handleInquiry = (e) => {
    e.preventDefault();
    if (!formData.name || !formData.phone) {
      toast.error('Please provide your name and contact phone number.');
      return;
    }
    setInquirySubmitted(true);
    toast.success('Thank you! Our Anand farm distribution team will contact you shortly.');
  };

  const products = [
    {
      name: 'Farm Fresh Buffalo Milk',
      badge: 'Bestseller',
      tagline: 'Raw, unadulterated full-cream milk',
      fat: '6.5% - 7.5% Natural Fat',
      price: '₹60.00 / Litre',
      desc: 'Chilled within 45 minutes of milking. Rich in calcium and A2 beta-casein with thick natural malai.',
      image: '/images/dairy_products_spread.jpg',
    },
    {
      name: 'Traditional Bilona Buffalo Ghee',
      badge: 'Artisanal',
      tagline: 'Slow-cooked golden aromatic ghee',
      fat: '100% Cultured Butter Fat',
      price: '₹950.00 / 1 Kg',
      desc: 'Crafted following the ancient Vedic bilona method: cultured dahi churned into makhan and slow-simmered.',
      image: '/images/dairy_products_spread.jpg',
    },
    {
      name: 'Fresh Malai Paneer',
      badge: 'Daily Fresh',
      tagline: 'Ultra-soft artisan cottage cheese',
      fat: 'High Protein & Soft Texture',
      price: '₹420.00 / 1 Kg',
      desc: 'Made daily from morning batch pure buffalo milk without artificial coagulants or starches.',
      image: '/images/dairy_products_spread.jpg',
    },
    {
      name: 'Thick Earthen Pot Buffalo Dahi',
      badge: 'Probiotic',
      tagline: 'Naturally fermented creamy curd',
      fat: 'Pure Cultured Probiotic',
      price: '₹80.00 / 1 Kg',
      desc: 'Set in traditional porous clay pots that absorb moisture, producing dense, naturally sweet curd.',
      image: '/images/dairy_products_spread.jpg',
    },
    {
      name: 'Pure Buffalo Mawa / Khoya',
      badge: 'Pure Solid',
      tagline: 'Slowly evaporated rich milk solids',
      fat: 'Ideal for Indian Sweets',
      price: '₹380.00 / 1 Kg',
      desc: 'Pure whole buffalo milk reduced in heavy iron kadhais without vegetable fats, chalk, or additives.',
      image: '/images/dairy_products_spread.jpg',
    },
    {
      name: 'Spiced Desi Chaas (Buttermilk)',
      badge: 'Refreshing',
      tagline: 'Churned buttermilk with herbs',
      fat: 'Low Calorie & Digestive',
      price: '₹25.00 / 500 ml',
      desc: 'Refreshing buttermilk seasoned with roasted cumin (jeera), Gujarat rock salt, and fresh mint leaves.',
      image: '/images/dairy_products_spread.jpg',
    },
  ];

  return (
    <div className="min-h-screen bg-slate-50 text-slate-800">
      {/* Top Banner */}
      <div className="bg-emerald-900 text-emerald-100 text-xs py-2 px-4 text-center font-medium">
        <span>📍 Farm Fresh Supply direct from Anand, Gujarat — The Milk Capital of India</span>
        <span className="hidden md:inline mx-3">•</span>
        <span className="hidden md:inline">Daily Delivery: 5:30 AM & 5:30 PM Slots</span>
      </div>

      {/* Navigation Header */}
      <header className="bg-white/95 backdrop-blur-md border-b border-slate-200 sticky top-0 z-40">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-20 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-11 h-11 rounded-2xl bg-emerald-600 text-white flex items-center justify-center font-bold text-xl shadow-md shadow-emerald-600/20">
              <Milk className="w-6 h-6" />
            </div>
            <div>
              <span className="font-extrabold text-slate-900 text-xl tracking-tight block leading-tight">
                AmritDhara Dairy
              </span>
              <span className="text-[10px] text-emerald-700 uppercase tracking-widest font-bold block">
                Pure Murrah Buffalo Farm • Anand
              </span>
            </div>
          </div>

          <nav className="hidden md:flex items-center gap-8 text-sm font-semibold text-slate-600">
            <a href="#about" className="hover:text-emerald-700 transition">About Farm</a>
            <a href="#products" className="hover:text-emerald-700 transition">Dairy Products</a>
            <a href="#facility" className="hover:text-emerald-700 transition">Processing & Hygiene</a>
            <a href="#distribution" className="hover:text-emerald-700 transition">Cold Chain</a>
            <a href="#contact" className="hover:text-emerald-700 transition">Contact & Inquiry</a>
          </nav>

          <div className="flex items-center gap-3">
            {isAuthenticated ? (
              <Link
                to="/dashboard"
                className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold shadow-md shadow-emerald-600/20 transition"
              >
                <span>Dashboard ({user?.role})</span>
                <ArrowRight className="w-4 h-4" />
              </Link>
            ) : (
              <Link
                to="/login"
                className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-slate-900 hover:bg-slate-800 text-white text-xs font-bold transition shadow-xs"
              >
                <span>Staff Portal</span>
                <ExternalLink className="w-3.5 h-3.5 text-emerald-400" />
              </Link>
            )}
          </div>
        </div>
      </header>

      {/* Hero Section */}
      <section className="relative overflow-hidden bg-gradient-to-b from-emerald-950 via-slate-900 to-emerald-900 text-white py-20 lg:py-28">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 relative z-10">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-12 items-center">
            <div className="lg:col-span-7 space-y-6">
              <div className="inline-flex items-center gap-2 px-3.5 py-1.5 rounded-full bg-emerald-500/20 border border-emerald-400/30 text-emerald-300 text-xs font-semibold uppercase tracking-wider">
                <ShieldCheck className="w-4 h-4 text-emerald-400" />
                <span>100% Pure Indian Murrah Buffalo Dairy</span>
              </div>

              <h1 className="text-4xl sm:text-5xl lg:text-6xl font-black tracking-tight text-white leading-tight">
                Farm-Pure Buffalo Milk & Handcrafted Dairy
              </h1>

              <p className="text-base sm:text-lg text-emerald-100/90 leading-relaxed max-w-2xl">
                Raised on certified organic green fodder in Anand, Gujarat. Ethically milked twice daily and delivered directly to households and sweet artisans with zero preservatives, hormones, or dilution.
              </p>

              <div className="flex flex-wrap gap-4 pt-2">
                <a
                  href="#products"
                  className="px-6 py-3.5 rounded-xl bg-emerald-500 hover:bg-emerald-600 text-slate-950 font-bold text-sm transition shadow-lg shadow-emerald-500/30 inline-flex items-center gap-2"
                >
                  <span>View Products & Rates</span>
                  <ArrowRight className="w-4 h-4" />
                </a>
                <a
                  href="#contact"
                  className="px-6 py-3.5 rounded-xl bg-white/10 hover:bg-white/20 border border-white/20 text-white font-semibold text-sm transition backdrop-blur-xs"
                >
                  Order Sample / Book Farm Visit
                </a>
              </div>

              {/* Badges Bar */}
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 pt-8 border-t border-emerald-800/60">
                <div>
                  <p className="text-2xl font-black text-emerald-400">60+</p>
                  <p className="text-xs text-slate-300 font-medium">Murrah Buffaloes</p>
                </div>
                <div>
                  <p className="text-2xl font-black text-emerald-400">1,400+ L</p>
                  <p className="text-xs text-slate-300 font-medium">Daily Milk Yield</p>
                </div>
                <div>
                  <p className="text-2xl font-black text-emerald-400">&lt; 4°C</p>
                  <p className="text-xs text-slate-300 font-medium">Instant Plate Chilling</p>
                </div>
                <div>
                  <p className="text-2xl font-black text-emerald-400">0%</p>
                  <p className="text-xs text-slate-300 font-medium">Hormones / Antibiotics</p>
                </div>
              </div>
            </div>

            {/* Hero Image Showcase */}
            <div className="lg:col-span-5 relative">
              <div className="relative rounded-3xl overflow-hidden shadow-2xl border-4 border-emerald-800/40">
                <img
                  src="/images/dairy_hero_farm.jpg"
                  alt="Murrah Buffalo herd in Indian green pasture"
                  className="w-full h-[440px] object-cover"
                />
                <div className="absolute inset-0 bg-gradient-to-t from-slate-950 via-slate-950/20 to-transparent" />
                <div className="absolute bottom-6 left-6 right-6 p-4 rounded-2xl bg-white/10 backdrop-blur-md border border-white/20">
                  <p className="text-xs font-semibold text-emerald-300 uppercase tracking-widest">
                    Live Farm Snapshot • Anand, Gujarat
                  </p>
                  <p className="text-sm font-bold text-white mt-0.5">
                    Healthy Murrah Herd with Free-Range Daily Grazing
                  </p>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* About The Farm & Sustainable Cooperative */}
      <section id="about" className="py-20 bg-white">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center max-w-3xl mx-auto mb-16">
            <span className="text-xs font-bold uppercase tracking-wider text-emerald-600 bg-emerald-50 px-3 py-1 rounded-full">
              Single-Farm Purity
            </span>
            <h2 className="text-3xl sm:text-4xl font-extrabold text-slate-900 mt-3">
              Rooted in the Soil of Anand, Gujarat
            </h2>
            <p className="text-slate-600 text-base mt-4 leading-relaxed">
              We operate an integrated single-farm dairy where every drop of milk comes directly from our own herd of high-pedigree Murrah buffaloes. No milk pooling, no third-party mixing, and zero middleman tampering.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
            <div className="p-8 rounded-2xl bg-slate-50 border border-slate-200 shadow-xs hover:border-emerald-300 transition">
              <div className="w-12 h-12 rounded-xl bg-emerald-100 text-emerald-700 flex items-center justify-center font-bold mb-6">
                <HeartHandshake className="w-6 h-6" />
              </div>
              <h3 className="text-lg font-bold text-slate-900 mb-2">Ethical Animal Husbandry</h3>
              <p className="text-sm text-slate-600 leading-relaxed">
                Our buffaloes are housed in well-ventilated barns with mist coolers and soft rubber bedding. They feed on fresh Napier grass, alfalfa, and non-GMO cattle grain rations.
              </p>
            </div>

            <div className="p-8 rounded-2xl bg-slate-50 border border-slate-200 shadow-xs hover:border-emerald-300 transition">
              <div className="w-12 h-12 rounded-xl bg-emerald-100 text-emerald-700 flex items-center justify-center font-bold mb-6">
                <ThermometerSnowflake className="w-6 h-6" />
              </div>
              <h3 className="text-lg font-bold text-slate-900 mb-2">Instant 4°C Plate Chilling</h3>
              <p className="text-sm text-slate-600 leading-relaxed">
                Milk is piped straight from automated milking clusters into a stainless-steel Bulk Milk Cooler (BMC) running at 4°C within 45 minutes to halt all bacterial development.
              </p>
            </div>

            <div className="p-8 rounded-2xl bg-slate-50 border border-slate-200 shadow-xs hover:border-emerald-300 transition">
              <div className="w-12 h-12 rounded-xl bg-emerald-100 text-emerald-700 flex items-center justify-center font-bold mb-6">
                <Award className="w-6 h-6" />
              </div>
              <h3 className="text-lg font-bold text-slate-900 mb-2">14-Point Quality Testing</h3>
              <p className="text-sm text-slate-600 leading-relaxed">
                Every milking session undergoes computerized digital testing for fat percentage, Solid-Not-Fat (SNF), adulterants, water dilution, and antibiotic residues.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Products Showcase */}
      <section id="products" className="py-20 bg-slate-100/70 border-y border-slate-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex flex-col md:flex-row md:items-end md:justify-between mb-14">
            <div>
              <span className="text-xs font-bold uppercase tracking-wider text-emerald-600 bg-emerald-100/70 px-3 py-1 rounded-full">
                Direct from Farm
              </span>
              <h2 className="text-3xl sm:text-4xl font-extrabold text-slate-900 mt-3">
                Our Fresh Products & Rates
              </h2>
              <p className="text-slate-600 text-sm mt-2 max-w-xl">
                All products are derived exclusively from 100% pure Murrah buffalo milk with transparent pricing in Indian Rupees (INR).
              </p>
            </div>
            <a
              href="#contact"
              className="mt-4 md:mt-0 inline-flex items-center gap-1.5 text-xs font-bold text-emerald-700 hover:text-emerald-800 transition"
            >
              Request Bulk & Commercial Supply Rates <ArrowRight className="w-4 h-4" />
            </a>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
            {products.map((prod) => (
              <div
                key={prod.name}
                className="bg-white rounded-2xl overflow-hidden border border-slate-200 shadow-xs hover:shadow-md transition flex flex-col"
              >
                <div className="relative h-52 overflow-hidden bg-slate-200">
                  <img
                    src={prod.image}
                    alt={prod.name}
                    className="w-full h-full object-cover hover:scale-105 transition duration-500"
                  />
                  <span className="absolute top-3 left-3 bg-slate-900/80 backdrop-blur-xs text-white text-[11px] font-bold px-2.5 py-1 rounded-lg uppercase tracking-wider">
                    {prod.badge}
                  </span>
                  <span className="absolute bottom-3 right-3 bg-emerald-600 text-white text-xs font-bold px-3 py-1 rounded-lg shadow-sm">
                    {prod.price}
                  </span>
                </div>

                <div className="p-6 flex-1 flex flex-col justify-between">
                  <div>
                    <h3 className="text-lg font-bold text-slate-900">{prod.name}</h3>
                    <p className="text-xs text-emerald-700 font-semibold mt-0.5">{prod.tagline}</p>
                    <p className="text-xs text-slate-500 mt-3 leading-relaxed">{prod.desc}</p>
                  </div>

                  <div className="mt-6 pt-4 border-t border-slate-100 flex items-center justify-between">
                    <span className="text-[11px] font-semibold text-slate-600 bg-slate-100 px-2.5 py-1 rounded-md">
                      {prod.fat}
                    </span>
                    <a
                      href="#contact"
                      className="text-xs font-bold text-emerald-600 hover:text-emerald-700 inline-flex items-center gap-1"
                    >
                      Order Supply <ArrowRight className="w-3.5 h-3.5" />
                    </a>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Modern Facility & Processing */}
      <section id="facility" className="py-20 bg-white">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-12 items-center">
            <div className="lg:col-span-6 space-y-6">
              <span className="text-xs font-bold uppercase tracking-wider text-emerald-600 bg-emerald-50 px-3 py-1 rounded-full">
                Infrastructure & Technology
              </span>
              <h2 className="text-3xl sm:text-4xl font-extrabold text-slate-900">
                Automated Processing Plant in Anand Industrial Zone
              </h2>
              <p className="text-slate-600 text-sm leading-relaxed">
                Our on-farm processing facility uses automated European milking clusters and ISO 9001 food-grade 304 stainless-steel pipelines. Milk travels directly from teat to tank without human exposure or air contamination.
              </p>

              <div className="space-y-3 pt-2">
                <div className="flex items-start gap-3">
                  <CheckCircle className="w-5 h-5 text-emerald-600 mt-0.5 shrink-0" />
                  <p className="text-xs sm:text-sm text-slate-700 font-medium">
                    Automated CIP (Clean-In-Place) sanitation cycles before and after every milking session.
                  </p>
                </div>
                <div className="flex items-start gap-3">
                  <CheckCircle className="w-5 h-5 text-emerald-600 mt-0.5 shrink-0" />
                  <p className="text-xs sm:text-sm text-slate-700 font-medium">
                    Continuous chiller temperature logging monitored via digital telemetry.
                  </p>
                </div>
                <div className="flex items-start gap-3">
                  <CheckCircle className="w-5 h-5 text-emerald-600 mt-0.5 shrink-0" />
                  <p className="text-xs sm:text-sm text-slate-700 font-medium">
                    Eco-friendly solar water heating and bio-gas energy recovery from livestock waste.
                  </p>
                </div>
              </div>
            </div>

            <div className="lg:col-span-6 grid grid-cols-2 gap-4">
              <img
                src="/images/dairy_processing_plant.jpg"
                alt="Automated dairy processing plant and stainless steel BMC chilling tanks"
                className="rounded-2xl shadow-sm object-cover h-56 w-full"
              />
              <img
                src="/images/dairy_distribution_van.jpg"
                alt="Temperature-controlled cold chain refrigerated milk distribution van in Gujarat"
                className="rounded-2xl shadow-sm object-cover h-56 w-full mt-6"
              />
            </div>
          </div>
        </div>
      </section>

      {/* Distribution & Cold Chain */}
      <section id="distribution" className="py-20 bg-slate-900 text-white">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="text-center max-w-3xl mx-auto mb-16">
            <span className="text-xs font-bold uppercase tracking-wider text-emerald-400 bg-emerald-950 px-3 py-1 rounded-full border border-emerald-800">
              Reliable Logistics
            </span>
            <h2 className="text-3xl sm:text-4xl font-extrabold text-white mt-3">
              Daily Cold-Chain Distribution Network
            </h2>
            <p className="text-slate-300 text-sm mt-3">
              Operating dedicated temperature-controlled vans to deliver morning and evening milk at peak freshness across central Gujarat.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-8 text-center">
            <div className="p-6 rounded-2xl bg-slate-800/80 border border-slate-700">
              <div className="w-12 h-12 rounded-xl bg-emerald-500/20 text-emerald-400 flex items-center justify-center mx-auto mb-4">
                <Clock className="w-6 h-6" />
              </div>
              <h3 className="text-base font-bold text-white mb-2">Slot 1: Morning Delivery</h3>
              <p className="text-xs text-slate-300 leading-relaxed">
                Dispatched at 5:00 AM. Reaches doorstep, local retail outlets, and tea stalls by 6:30 AM before breakfast.
              </p>
            </div>

            <div className="p-6 rounded-2xl bg-slate-800/80 border border-slate-700">
              <div className="w-12 h-12 rounded-xl bg-emerald-500/20 text-emerald-400 flex items-center justify-center mx-auto mb-4">
                <Truck className="w-6 h-6" />
              </div>
              <h3 className="text-base font-bold text-white mb-2">Insulated Fleet</h3>
              <p className="text-xs text-slate-300 leading-relaxed">
                Refrigerated insulated transit boxes maintaining cold chain temperature below 4°C throughout transport.
              </p>
            </div>

            <div className="p-6 rounded-2xl bg-slate-800/80 border border-slate-700">
              <div className="w-12 h-12 rounded-xl bg-emerald-500/20 text-emerald-400 flex items-center justify-center mx-auto mb-4">
                <Clock className="w-6 h-6" />
              </div>
              <h3 className="text-base font-bold text-white mb-2">Slot 2: Evening Milking</h3>
              <p className="text-xs text-slate-300 leading-relaxed">
                Dispatched at 5:00 PM. Delivered for evening household dinners and fresh evening sweet preparation.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* Customer Contact & Inquiry Form */}
      <section id="contact" className="py-20 bg-white">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-12">
            <div className="lg:col-span-5 space-y-6">
              <span className="text-xs font-bold uppercase tracking-wider text-emerald-600 bg-emerald-50 px-3 py-1 rounded-full">
                Get In Touch
              </span>
              <h2 className="text-3xl font-extrabold text-slate-900">
                Supply Inquiries & Farm Visits
              </h2>
              <p className="text-slate-600 text-sm leading-relaxed">
                We supply fresh buffalo milk and artisanal dairy to local households, hotels, sweets manufacturers, and caterers across Anand, Nadiad, and Vadodara.
              </p>

              <div className="space-y-4 pt-4 border-t border-slate-100">
                <div className="flex items-start gap-3">
                  <MapPin className="w-5 h-5 text-emerald-600 mt-1 shrink-0" />
                  <div>
                    <p className="text-xs font-bold uppercase tracking-wider text-slate-400">Farm & Plant Address</p>
                    <p className="text-sm font-semibold text-slate-800">
                      Survey No. 142/A, Dairy Cooperative Belt, Anand - 388001, Gujarat, India
                    </p>
                  </div>
                </div>

                <div className="flex items-start gap-3">
                  <Phone className="w-5 h-5 text-emerald-600 mt-1 shrink-0" />
                  <div>
                    <p className="text-xs font-bold uppercase tracking-wider text-slate-400">Direct Farm Hotline</p>
                    <p className="text-sm font-semibold text-slate-800">+91 98765 43210 / +91 2692 245678</p>
                  </div>
                </div>

                <div className="flex items-start gap-3">
                  <Mail className="w-5 h-5 text-emerald-600 mt-1 shrink-0" />
                  <div>
                    <p className="text-xs font-bold uppercase tracking-wider text-slate-400">Email Inquiries</p>
                    <p className="text-sm font-semibold text-slate-800">orders@amritdharadairy.in</p>
                  </div>
                </div>
              </div>
            </div>

            <div className="lg:col-span-7">
              <div className="bg-slate-50 p-8 rounded-3xl border border-slate-200 shadow-sm">
                <h3 className="text-lg font-bold text-slate-900 mb-1">Send a Direct Message</h3>
                <p className="text-xs text-slate-500 mb-6">
                  Fill in your details below to schedule a subscription trial or bulk commercial rate sheet.
                </p>

                {inquirySubmitted ? (
                  <div className="p-6 bg-emerald-50 border border-emerald-200 rounded-2xl text-center">
                    <CheckCircle className="w-10 h-10 text-emerald-600 mx-auto mb-3" />
                    <h4 className="text-base font-bold text-emerald-900">Inquiry Received</h4>
                    <p className="text-xs text-emerald-700 mt-1">
                      Our dispatch manager will call you within 2 business hours.
                    </p>
                    <button
                      type="button"
                      onClick={() => setInquirySubmitted(false)}
                      className="mt-4 text-xs font-bold text-emerald-800 underline"
                    >
                      Send another request
                    </button>
                  </div>
                ) : (
                  <form onSubmit={handleInquiry} className="space-y-4">
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                      <div>
                        <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1">
                          Your Name
                        </label>
                        <input
                          type="text"
                          required
                          value={formData.name}
                          onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                          placeholder="e.g. Ramesh Patel"
                          className="w-full px-3.5 py-2.5 text-sm rounded-lg border border-slate-300 focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500 bg-white"
                        />
                      </div>
                      <div>
                        <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1">
                          Phone Number (WhatsApp)
                        </label>
                        <input
                          type="tel"
                          required
                          value={formData.phone}
                          onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
                          placeholder="+91 98765 00000"
                          className="w-full px-3.5 py-2.5 text-sm rounded-lg border border-slate-300 focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500 bg-white"
                        />
                      </div>
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                      <div>
                        <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1">
                          Email Address
                        </label>
                        <input
                          type="email"
                          value={formData.email}
                          onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                          placeholder="ramesh@example.com"
                          className="w-full px-3.5 py-2.5 text-sm rounded-lg border border-slate-300 focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500 bg-white"
                        />
                      </div>
                      <div>
                        <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1">
                          Interested In
                        </label>
                        <select
                          value={formData.product}
                          onChange={(e) => setFormData({ ...formData, product: e.target.value })}
                          className="w-full px-3.5 py-2.5 text-sm rounded-lg border border-slate-300 focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500 bg-white"
                        >
                          <option>Farm Fresh Buffalo Milk</option>
                          <option>Traditional Bilona Ghee</option>
                          <option>Fresh Malai Paneer</option>
                          <option>Set Clay Pot Curd</option>
                          <option>Bulk Sweet Manufacturing Supply</option>
                          <option>Book a Weekend Farm Visit</option>
                        </select>
                      </div>
                    </div>

                    <div>
                      <label className="block text-xs font-semibold uppercase tracking-wider text-slate-700 mb-1">
                        Requirement or Delivery Address
                      </label>
                      <textarea
                        rows={3}
                        value={formData.message}
                        onChange={(e) => setFormData({ ...formData, message: e.target.value })}
                        placeholder="Mention daily required litres, area in Anand/Vadodara, or special dietary requirements..."
                        className="w-full px-3.5 py-2.5 text-sm rounded-lg border border-slate-300 focus:ring-2 focus:ring-emerald-500 focus:border-emerald-500 bg-white"
                      />
                    </div>

                    <button
                      type="submit"
                      className="w-full py-3 px-4 rounded-xl bg-emerald-600 hover:bg-emerald-700 text-white font-bold text-sm shadow-md shadow-emerald-600/20 transition flex items-center justify-center gap-2 cursor-pointer"
                    >
                      <Send className="w-4 h-4" />
                      <span>Submit Inquiry to Anand Operations</span>
                    </button>
                  </form>
                )}
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="bg-slate-950 text-slate-400 text-xs py-12 border-t border-slate-800">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="grid grid-cols-1 md:grid-cols-4 gap-8 pb-10 border-b border-slate-800">
            <div className="md:col-span-2 space-y-3">
              <div className="flex items-center gap-2 text-white font-bold text-lg">
                <Milk className="w-5 h-5 text-emerald-400" />
                <span>AmritDhara Buffalo Dairy</span>
              </div>
              <p className="text-slate-400 text-xs leading-relaxed max-w-md">
                Certified single-farm buffalo dairy dedicated to unadulterated freshness, organic fodder, and ethical animal husbandry in Anand, Gujarat.
              </p>
              <p className="text-emerald-400 text-[11px] font-mono">
                FSSAI License: 10723019000124 • GSTIN: 24AAACA0000A1Z5
              </p>
            </div>

            <div>
              <p className="text-white font-bold text-xs uppercase tracking-wider mb-3">Quick Links</p>
              <ul className="space-y-2">
                <li><a href="#about" className="hover:text-emerald-400 transition">About the Farm</a></li>
                <li><a href="#products" className="hover:text-emerald-400 transition">Our Dairy Products</a></li>
                <li><a href="#facility" className="hover:text-emerald-400 transition">Processing Facility</a></li>
                <li><a href="#distribution" className="hover:text-emerald-400 transition">Cold Chain Schedule</a></li>
              </ul>
            </div>

            <div>
              <p className="text-white font-bold text-xs uppercase tracking-wider mb-3">Internal Access</p>
              <p className="text-slate-400 text-xs mb-3">
                Authorized farm operators and managers access the internal live inventory and production grid:
              </p>
              <Link
                to="/login"
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white font-semibold transition"
              >
                <span>Staff Portal Sign In</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </Link>
            </div>
          </div>

          <div className="pt-6 flex flex-col sm:flex-row items-center justify-between text-[11px] text-slate-500">
            <p>© {new Date().getFullYear()} AmritDhara Buffalo Dairy & Processing Co-op. All rights reserved.</p>
            <p className="mt-2 sm:mt-0">Powered by DairyFlow Operations System (Asia/Kolkata)</p>
          </div>
        </div>
      </footer>
    </div>
  );
}

export default Landing;
