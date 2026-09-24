import { useEffect, useRef, useState } from "react";

interface LandingPageProps {
  onEnterApp: (targetView?: "reconciliation" | "overview" | "reviews" | "conflicts" | "memory" | "schedule") => void;
}

export function LandingPage({ onEnterApp }: LandingPageProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [selectedScenario, setSelectedScenario] = useState<number>(0);
  const [tickerIndex, setTickerIndex] = useState(0);

  // Rotating telemetry ticker
  const tickerItems = [
    "RECONCILED: 3 contradictory daily challans on Nagpur Metro Pier P-12 with drone point-cloud (96.2% confidence)",
    "GATEKEEPER ACTIVE: Blocked unauthorized 100% completion claim on Abutment A-1 (Drone confirms 58%)",
    "SCHEDULE SYNC: Planner approved +140m grade fill into Primavera P6 without manual data entry",
    "MULTI-SOURCE AUDIT: Merged WhatsApp site photo + TotalStation telemetry into unified audit hash #a9f24b",
  ];

  useEffect(() => {
    const timer = setInterval(() => {
      setTickerIndex((prev) => (prev + 1) % tickerItems.length);
    }, 4000);
    return () => clearInterval(timer);
  }, [tickerItems.length]);

  // Interactive Digital Twin / LiDAR Grid Animation on Canvas
  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    let animationFrameId: number;
    let width = (canvas.width = canvas.offsetWidth);
    let height = (canvas.height = canvas.offsetHeight);

    const handleResize = () => {
      if (!canvas) return;
      width = canvas.width = canvas.offsetWidth;
      height = canvas.height = canvas.offsetHeight;
    };
    window.addEventListener("resize", handleResize);

    // Particle nodes representing LiDAR survey points
    const points: Array<{ x: number; y: number; vx: number; vy: number; elevation: number }> = [];
    const count = 45;
    for (let i = 0; i < count; i++) {
      points.push({
        x: Math.random() * width,
        y: Math.random() * height,
        vx: (Math.random() - 0.5) * 0.4,
        vy: (Math.random() - 0.5) * 0.4,
        elevation: Math.floor(Math.random() * 40 + 110),
      });
    }

    let scanY = 0;

    const render = () => {
      ctx.clearRect(0, 0, width, height);

      // 1. Perspective grid
      ctx.strokeStyle = "rgba(14, 165, 233, 0.08)";
      ctx.lineWidth = 1;
      const gridSize = 60;
      for (let x = 0; x < width; x += gridSize) {
        ctx.beginPath();
        ctx.moveTo(x, 0);
        ctx.lineTo(x, height);
        ctx.stroke();
      }
      for (let y = 0; y < height; y += gridSize) {
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(width, y);
        ctx.stroke();
      }

      // 2. Animated scanning beam
      scanY = (scanY + 1.2) % height;
      const gradient = ctx.createLinearGradient(0, scanY - 60, 0, scanY);
      gradient.addColorStop(0, "rgba(13, 148, 136, 0)");
      gradient.addColorStop(1, "rgba(13, 148, 136, 0.18)");
      ctx.fillStyle = gradient;
      ctx.fillRect(0, scanY - 60, width, 60);

      ctx.strokeStyle = "rgba(20, 184, 166, 0.6)";
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(0, scanY);
      ctx.lineTo(width, scanY);
      ctx.stroke();

      // 3. LiDAR Points & connections
      ctx.fillStyle = "rgba(45, 212, 191, 0.85)";
      ctx.font = "9px monospace";

      for (let i = 0; i < points.length; i++) {
        const p = points[i];
        p.x += p.vx;
        p.y += p.vy;
        if (p.x < 0) p.x = width;
        if (p.x > width) p.x = 0;
        if (p.y < 0) p.y = height;
        if (p.y > height) p.y = 0;

        // Point
        ctx.beginPath();
        ctx.arc(p.x, p.y, 2, 0, Math.PI * 2);
        ctx.fill();

        // Connect nearby points
        for (let j = i + 1; j < points.length; j++) {
          const p2 = points[j];
          const dist = Math.hypot(p.x - p2.x, p.y - p2.y);
          if (dist < 110) {
            ctx.strokeStyle = `rgba(14, 165, 233, ${0.18 * (1 - dist / 110)})`;
            ctx.lineWidth = 0.8;
            ctx.beginPath();
            ctx.moveTo(p.x, p.y);
            ctx.lineTo(p2.x, p2.y);
            ctx.stroke();
          }
        }
      }

      animationFrameId = requestAnimationFrame(render);
    };

    render();

    return () => {
      window.removeEventListener("resize", handleResize);
      cancelAnimationFrame(animationFrameId);
    };
  }, []);

  const scenarios = [
    {
      title: "Contractor 100% Claim vs. Drone 58%",
      type: "QUANTITY DISCREPANCY",
      severity: "CRITICAL",
      description: "Subcontractor submitted final payment bill claiming 100% completion on Pier Cap C-12. Computer Vision photogrammetry from morning drone flight measured only 58.4% casting progress.",
      resolution: "AI flags 41.6% phantom progress, halts automatic billing, and isolates Pier Cap C-12 for mandatory planner review.",
      confidence: "98.7%",
      recommendation: "Reject claim, issue site deficiency notice, lock schedule baseline.",
    },
    {
      title: "Contradictory Daily Weather Delay",
      type: "TEMPORAL CONFLICT",
      severity: "MODERATE",
      description: "Site WhatsApp log claimed full-day shutdown due to torrential rain. Automated IoT weather telemetry station 400m away recorded only 1.2mm total precipitation.",
      resolution: "Reconciliation engine cross-references satellite radar data, identifies localized cloudburst, and permits a partial 3-hour non-critical adjustment instead of full day.",
      confidence: "92.4%",
      recommendation: "Approve 3.5h delay allocation; flag contractor for repeated adverse weather inflation.",
    },
    {
      title: "Duplicate Reinforcement Steel Delivery",
      type: "MATERIAL CHALLAN DUPLICATE",
      severity: "HIGH",
      description: "Two delivery weighbridge slips entered with matching 24-ton grade Fe500D rebar manifests 18 minutes apart under differing handwritten invoice numbers.",
      resolution: "NLP invoice parsing detected identical truck registration plate (MH-31-CB-8491) and identical gross tare weight signature.",
      confidence: "99.1%",
      recommendation: "Auto-merge duplicate receipts into single entry; prevent double-counting inventory in Schedule WBS.",
    },
  ];

  return (
    <div style={{ background: "#080B10", color: "#F0F6FC", minHeight: "100vh", fontFamily: "system-ui, -apple-system, sans-serif" }}>
      
      {/* ============================================================ */}
      {/* 1. CINEMATIC TOP NAV BAR */}
      {/* ============================================================ */}
      <header
        style={{
          position: "sticky",
          top: 0,
          zIndex: 100,
          background: "rgba(8, 11, 16, 0.85)",
          backdropFilter: "blur(12px)",
          WebkitBackdropFilter: "blur(12px)",
          borderBottom: "1px solid rgba(255, 255, 255, 0.08)",
          padding: "14px 28px",
        }}
      >
        <div style={{ maxWidth: 1400, margin: "0 auto", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          
          {/* Brand */}
          <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
            <div
              style={{
                width: 38,
                height: 38,
                borderRadius: 10,
                background: "linear-gradient(135deg, #0D9488 0%, #0284C7 100%)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                fontWeight: 900,
                fontSize: 18,
                color: "#FFFFFF",
                boxShadow: "0 0 20px rgba(13, 148, 136, 0.4)",
              }}
            >
              CP
            </div>
            <div>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <span style={{ fontSize: 16, fontWeight: 800, letterSpacing: "-0.02em", color: "#FFFFFF" }}>
                  CognitiveProgress
                </span>
                <span
                  style={{
                    fontSize: 10,
                    fontWeight: 700,
                    background: "rgba(13, 148, 136, 0.2)",
                    color: "#2DD4BF",
                    border: "1px solid rgba(45, 212, 191, 0.3)",
                    padding: "2px 7px",
                    borderRadius: 999,
                    letterSpacing: "0.04em",
                  }}
                >
                  Enterprise Edition
                </span>
              </div>
              <p style={{ margin: 0, fontSize: 11, color: "#8B949E" }}>Autonomous Progress Reconciliation Engine</p>
            </div>
          </div>

          {/* Nav Links */}
          <nav style={{ display: "flex", alignItems: "center", gap: 24 }}>
            <a href="#pipeline" style={{ color: "#8B949E", textDecoration: "none", fontSize: 13, fontWeight: 500, transition: "color 0.2s" }} onMouseEnter={(e) => (e.currentTarget.style.color = "#FFFFFF")} onMouseLeave={(e) => (e.currentTarget.style.color = "#8B949E")}>
              Engine Pipeline
            </a>
            <a href="#split-reality" style={{ color: "#8B949E", textDecoration: "none", fontSize: 13, fontWeight: 500, transition: "color 0.2s" }} onMouseEnter={(e) => (e.currentTarget.style.color = "#FFFFFF")} onMouseLeave={(e) => (e.currentTarget.style.color = "#8B949E")}>
              Split Reality
            </a>
            <a href="#simulator" style={{ color: "#8B949E", textDecoration: "none", fontSize: 13, fontWeight: 500, transition: "color 0.2s" }} onMouseEnter={(e) => (e.currentTarget.style.color = "#FFFFFF")} onMouseLeave={(e) => (e.currentTarget.style.color = "#8B949E")}>
              Conflict Simulator
            </a>
            <a href="#specs" style={{ color: "#8B949E", textDecoration: "none", fontSize: 13, fontWeight: 500, transition: "color 0.2s" }} onMouseEnter={(e) => (e.currentTarget.style.color = "#FFFFFF")} onMouseLeave={(e) => (e.currentTarget.style.color = "#8B949E")}>
              Architecture
            </a>
          </nav>

          {/* Action CTAs */}
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <button
              onClick={() => onEnterApp("reviews")}
              style={{
                background: "rgba(255, 255, 255, 0.05)",
                border: "1px solid rgba(255, 255, 255, 0.15)",
                color: "#E6EDF3",
                padding: "8px 16px",
                borderRadius: 8,
                fontSize: 13,
                fontWeight: 600,
                cursor: "pointer",
                transition: "all 0.2s",
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = "rgba(255, 255, 255, 0.1)";
                e.currentTarget.style.borderColor = "rgba(255, 255, 255, 0.3)";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = "rgba(255, 255, 255, 0.05)";
                e.currentTarget.style.borderColor = "rgba(255, 255, 255, 0.15)";
              }}
            >
              Planner Review Gate
            </button>

            <button
              onClick={() => onEnterApp("reconciliation")}
              style={{
                background: "linear-gradient(135deg, #0D9488 0%, #0284C7 100%)",
                border: "none",
                color: "#FFFFFF",
                padding: "8px 18px",
                borderRadius: 8,
                fontSize: 13,
                fontWeight: 700,
                cursor: "pointer",
                boxShadow: "0 0 16px rgba(13, 148, 136, 0.4)",
                display: "flex",
                alignItems: "center",
                gap: 6,
                transition: "transform 0.15s, box-shadow 0.15s",
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.transform = "translateY(-1px)";
                e.currentTarget.style.boxShadow = "0 0 24px rgba(13, 148, 136, 0.6)";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.transform = "none";
                e.currentTarget.style.boxShadow = "0 0 16px rgba(13, 148, 136, 0.4)";
              }}
            >
              <span>Launch Mission Control</span>
              <span>→</span>
            </button>
          </div>

        </div>
      </header>

      {/* ============================================================ */}
      {/* 2. CINEMATIC HERO WITH MOVING VIDEO & CANVAS HUD */}
      {/* ============================================================ */}
      <section
        style={{
          position: "relative",
          minHeight: "calc(100vh - 70px)",
          display: "flex",
          flexDirection: "column",
          justifyContent: "center",
          alignItems: "center",
          padding: "60px 24px 80px",
          overflow: "hidden",
        }}
      >
        {/* Background Video Layer - Visibly Clear & Cinematic */}
        <video
          autoPlay
          muted
          loop
          playsInline
          style={{
            position: "absolute",
            top: 0,
            left: 0,
            width: "100%",
            height: "100%",
            objectFit: "cover",
            objectPosition: "center center",
            opacity: 0.68,
            filter: "contrast(1.06) saturate(1.12) brightness(0.92)",
            zIndex: 0,
            pointerEvents: "none",
            backgroundColor: "transparent",
          }}
        >
          <source src="/videos/cognitiveprogress-hero.mp4" type="video/mp4" />
        </video>

        {/* Digital Twin LiDAR Canvas (Renders subtle laser telemetry over physical footage) */}
        <canvas
          ref={canvasRef}
          style={{
            position: "absolute",
            top: 0,
            left: 0,
            width: "100%",
            height: "100%",
            zIndex: 1,
            pointerEvents: "none",
          }}
        />

        {/* Smart Layer 1: Ambient Top & Bottom Edge Blending (Anchors Nav and Smoothly Transitions to Next Section) */}
        <div
          style={{
            position: "absolute",
            inset: 0,
            background:
              "linear-gradient(180deg, rgba(8, 11, 16, 0.5) 0%, rgba(8, 11, 16, 0.12) 25%, rgba(8, 11, 16, 0.2) 65%, #080B10 100%)",
            zIndex: 2,
            pointerEvents: "none",
          }}
        />

        {/* Smart Layer 2: Targeted Central Readability (Soft Darkening Directly Behind Typography While Leaving Sides & Footage Clear) */}
        <div
          style={{
            position: "absolute",
            inset: 0,
            background:
              "radial-gradient(ellipse 70% 60% at 50% 46%, rgba(8, 11, 16, 0.68) 0%, rgba(8, 11, 16, 0.28) 55%, transparent 100%)",
            zIndex: 2,
            pointerEvents: "none",
          }}
        />

        {/* HUD Telemetry Badges (Floating on Left & Right on Large Screens) */}
        <div
          className="hidden lg:flex"
          style={{
            position: "absolute",
            top: 30,
            left: 32,
            zIndex: 3,
            flexDirection: "column",
            gap: 6,
            fontFamily: "monospace",
            fontSize: 11,
            color: "rgba(45, 212, 191, 0.9)",
            background: "rgba(8, 11, 16, 0.7)",
            backdropFilter: "blur(10px)",
            border: "1px solid rgba(45, 212, 191, 0.25)",
            padding: "10px 16px",
            borderRadius: 8,
            boxShadow: "0 8px 24px rgba(0, 0, 0, 0.4)",
          }}
        >
          <div>● TELEMETRY: MATRICE-300 RTK // FIXED</div>
          <div style={{ color: "#8B949E" }}>LAT: 21.1458° N • LON: 79.0882° E</div>
          <div style={{ color: "#8B949E" }}>ALT: 124.6M • SATS: 18 • HDOP: 0.8</div>
        </div>

        <div
          className="hidden lg:flex"
          style={{
            position: "absolute",
            top: 30,
            right: 32,
            zIndex: 3,
            flexDirection: "column",
            gap: 6,
            fontFamily: "monospace",
            fontSize: 11,
            color: "rgba(56, 189, 248, 0.9)",
            background: "rgba(8, 11, 16, 0.7)",
            backdropFilter: "blur(10px)",
            border: "1px solid rgba(56, 189, 248, 0.25)",
            padding: "10px 16px",
            borderRadius: 8,
            textAlign: "right",
            boxShadow: "0 8px 24px rgba(0, 0, 0, 0.4)",
          }}
        >
          <div>PROJECT: NHAI-PKG-IV-VIADUCT</div>
          <div style={{ color: "#8B949E" }}>WBS LEVEL: L5/L6 SEMANTIC MATCH</div>
          <div style={{ color: "#34D399" }}>RECONCILIATION ENGINE: ONLINE</div>
        </div>

        {/* Hero Central Content */}
        <div style={{ position: "relative", zIndex: 5, maxWidth: 960, textAlign: "center" }}>
          
          {/* Top Pill */}
          <div
            style={{
              display: "inline-flex",
              alignItems: "center",
              gap: 8,
              background: "rgba(13, 148, 136, 0.15)",
              border: "1px solid rgba(45, 212, 191, 0.4)",
              borderRadius: 999,
              padding: "6px 18px",
              marginBottom: 24,
              boxShadow: "0 0 20px rgba(13, 148, 136, 0.2)",
            }}
          >
            <span style={{ width: 8, height: 8, borderRadius: "50%", background: "#2DD4BF", boxShadow: "0 0 10px #2DD4BF", display: "inline-block" }} />
            <span style={{ fontSize: 12, fontWeight: 700, color: "#2DD4BF", letterSpacing: "0.06em", textTransform: "uppercase" }}>
              Enterprise Schedule Intelligence • Automated Reconciliation
            </span>
          </div>

          {/* Giant Title */}
          <h1
            style={{
              fontSize: "clamp(42px, 5.5vw, 68px)",
              fontWeight: 900,
              lineHeight: 1.08,
              letterSpacing: "-0.03em",
              margin: "0 0 24px",
              color: "#FFFFFF",
              textShadow: "0 2px 24px rgba(0,0,0,0.95), 0 0 50px rgba(0,0,0,0.8)",
            }}
          >
            Where Concrete Meets <br />
            <span
              style={{
                background: "linear-gradient(135deg, #2DD4BF 0%, #38BDF8 50%, #7DD3FC 100%)",
                WebkitBackgroundClip: "text",
                WebkitTextFillColor: "transparent",
                filter: "drop-shadow(0 2px 16px rgba(0, 0, 0, 0.9))",
              }}
            >
              Autonomous Truth.
            </span>
          </h1>

          {/* Subtitle */}
          <p
            style={{
              fontSize: "clamp(16px, 1.8vw, 20px)",
              lineHeight: 1.65,
              color: "#F1F5F9",
              maxWidth: 780,
              margin: "0 auto 36px",
              fontWeight: 500,
              textShadow: "0 1px 12px rgba(0,0,0,0.95), 0 2px 24px rgba(0,0,0,0.85)",
            }}
          >
            Stop relying on delayed site WhatsApp messages and conflicting contractor claims.
            CognitiveProgress autonomously ingests drone telemetry, daily logs, and site challans — reconciling
            contradictions into verified, audit-ready Primavera P6 &amp; MS Project updates.
          </p>

          {/* Big Hero CTAs */}
          <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 16, flexWrap: "wrap" }}>
            <button
              onClick={() => onEnterApp("reconciliation")}
              style={{
                background: "linear-gradient(135deg, #0D9488 0%, #0284C7 100%)",
                border: "none",
                color: "#FFFFFF",
                padding: "16px 36px",
                borderRadius: 12,
                fontSize: 16,
                fontWeight: 700,
                cursor: "pointer",
                boxShadow: "0 10px 30px rgba(13, 148, 136, 0.5), 0 4px 16px rgba(0,0,0,0.6)",
                display: "flex",
                alignItems: "center",
                gap: 10,
                transition: "all 0.2s",
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.transform = "translateY(-2px)";
                e.currentTarget.style.boxShadow = "0 14px 40px rgba(13, 148, 136, 0.7)";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.transform = "none";
                e.currentTarget.style.boxShadow = "0 10px 30px rgba(13, 148, 136, 0.5), 0 4px 16px rgba(0,0,0,0.6)";
              }}
            >
              <span>Launch Mission Control</span>
              <span style={{ fontSize: 18 }}>→</span>
            </button>

            <button
              onClick={() => {
                const el = document.getElementById("simulator");
                el?.scrollIntoView({ behavior: "smooth" });
              }}
              style={{
                background: "rgba(8, 11, 16, 0.65)",
                border: "1px solid rgba(255, 255, 255, 0.28)",
                color: "#F0F6FC",
                padding: "16px 30px",
                borderRadius: 12,
                fontSize: 15,
                fontWeight: 600,
                cursor: "pointer",
                backdropFilter: "blur(12px)",
                boxShadow: "0 4px 16px rgba(0,0,0,0.4)",
                transition: "all 0.2s",
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = "rgba(255, 255, 255, 0.14)";
                e.currentTarget.style.borderColor = "rgba(255, 255, 255, 0.45)";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = "rgba(8, 11, 16, 0.65)";
                e.currentTarget.style.borderColor = "rgba(255, 255, 255, 0.28)";
              }}
            >
              Inspect Conflict Simulator ↓
            </button>

            <button
              onClick={() => onEnterApp("overview")}
              style={{
                background: "rgba(8, 11, 16, 0.5)",
                border: "1px solid rgba(45, 212, 191, 0.4)",
                color: "#2DD4BF",
                padding: "16px 24px",
                borderRadius: 12,
                fontSize: 15,
                fontWeight: 600,
                cursor: "pointer",
                backdropFilter: "blur(10px)",
                boxShadow: "0 4px 16px rgba(0,0,0,0.4)",
                transition: "all 0.2s",
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = "rgba(45, 212, 191, 0.15)";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = "rgba(8, 11, 16, 0.5)";
              }}
            >
              View Live Telemetry
            </button>
          </div>

          {/* Quick Stats Grid - Responsive across Mobile to 4K */}
          <div
            className="grid grid-cols-2 md:grid-cols-4 gap-4"
            style={{
              marginTop: 52,
              background: "rgba(8, 11, 16, 0.72)",
              border: "1px solid rgba(255, 255, 255, 0.14)",
              borderRadius: 14,
              padding: "20px 24px",
              backdropFilter: "blur(14px)",
              boxShadow: "0 16px 40px rgba(0, 0, 0, 0.5)",
            }}
          >
            <div>
              <div style={{ fontSize: 26, fontWeight: 800, color: "#2DD4BF" }}>100%</div>
              <div style={{ fontSize: 12, color: "#8B949E", marginTop: 2 }}>Automated Extraction</div>
            </div>
            <div>
              <div style={{ fontSize: 26, fontWeight: 800, color: "#38BDF8" }}>0 sec</div>
              <div style={{ fontSize: 12, color: "#8B949E", marginTop: 2 }}>Manual Excel Entry</div>
            </div>
            <div>
              <div style={{ fontSize: 26, fontWeight: 800, color: "#FBBF24" }}>3-Way</div>
              <div style={{ fontSize: 12, color: "#8B949E", marginTop: 2 }}>Conflict Cross-Check</div>
            </div>
            <div>
              <div style={{ fontSize: 26, fontWeight: 800, color: "#A78BFA" }}>Audit Hash</div>
              <div style={{ fontSize: 12, color: "#8B949E", marginTop: 2 }}>Tamper-Proof Trail</div>
            </div>
          </div>

        </div>

        {/* Live Horizon Telemetry Ticker */}
        <div
          style={{
            position: "absolute",
            bottom: 0,
            left: 0,
            right: 0,
            zIndex: 10,
            background: "rgba(8, 11, 16, 0.92)",
            borderTop: "1px solid rgba(45, 212, 191, 0.2)",
            padding: "10px 24px",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 12,
            fontFamily: "monospace",
            fontSize: 12,
          }}
        >
          <span style={{ color: "#2DD4BF", fontWeight: 700 }}>[LIVE RECONCILIATION RADAR]:</span>
          <span style={{ color: "#E6EDF3", transition: "all 0.5s" }}>{tickerItems[tickerIndex]}</span>
        </div>
      </section>

      {/* ============================================================ */}
      {/* 3. SPLIT REALITY: CHAOS VS. COGNITIVE TRUTH */}
      {/* ============================================================ */}
      <section id="split-reality" style={{ padding: "90px 24px", maxWidth: 1240, margin: "0 auto" }}>
        <div style={{ textAlign: "center", marginBottom: 54 }}>
          <span style={{ fontSize: 12, fontWeight: 700, color: "#38BDF8", letterSpacing: "0.08em", textTransform: "uppercase" }}>
            The Industry Paradigm Shift
          </span>
          <h2 style={{ fontSize: 36, fontWeight: 800, color: "#FFFFFF", margin: "10px 0 14px" }}>
            The Split-Reality Architecture
          </h2>
          <p style={{ color: "#8B949E", maxWidth: 640, margin: "0 auto", fontSize: 15, lineHeight: 1.6 }}>
            Legacy infrastructure projects hemorrhage budget because site reality is disconnected from project schedules.
            CognitiveProgress replaces subjective human reporting with mathematical certainty.
          </p>
        </div>

        <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24 }}>
          
          {/* Legacy Chaos Card */}
          <div
            style={{
              background: "rgba(22, 19, 21, 0.75)",
              border: "1px solid rgba(239, 68, 68, 0.3)",
              borderRadius: 16,
              padding: "32px 28px",
              position: "relative",
              overflow: "hidden",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20 }}>
              <span style={{ fontSize: 12, fontWeight: 800, color: "#F87171", letterSpacing: "0.05em", textTransform: "uppercase" }}>
                Current Reality • Fragmented &amp; Blind
              </span>
              <span style={{ fontSize: 11, color: "#F87171", background: "rgba(239, 68, 68, 0.15)", padding: "4px 8px", borderRadius: 6 }}>
                High Financial Risk
              </span>
            </div>
            <h3 style={{ fontSize: 22, fontWeight: 700, color: "#FFFFFF", margin: "0 0 16px" }}>
              The "Excel &amp; WhatsApp" Black Hole
            </h3>
            <ul style={{ listStyle: "none", padding: 0, margin: "0 0 24px", display: "flex", flexDirection: "column", gap: 14, color: "#D1D5DB", fontSize: 14 }}>
              <li style={{ display: "flex", gap: 10 }}>
                <span style={{ color: "#EF4444", fontWeight: 700 }}>✕</span>
                <span><strong>Unchecked Claims:</strong> Subcontractors invoice 100% completion while concrete is still curing on site.</span>
              </li>
              <li style={{ display: "flex", gap: 10 }}>
                <span style={{ color: "#EF4444", fontWeight: 700 }}>✕</span>
                <span><strong>4-Week Information Latency:</strong> Site events reach the Primavera P6 schedule weeks after delays have compounded.</span>
              </li>
              <li style={{ display: "flex", gap: 10 }}>
                <span style={{ color: "#EF4444", fontWeight: 700 }}>✕</span>
                <span><strong>Blinded Planners:</strong> Project managers spend 70% of their time reconciling contradictory spreadsheets instead of engineering.</span>
              </li>
            </ul>
            <div style={{ background: "rgba(0,0,0,0.4)", borderRadius: 8, padding: "14px 16px", border: "1px dashed rgba(239, 68, 68, 0.3)", fontFamily: "monospace", fontSize: 12, color: "#FCA5A5" }}>
              <div>[!] Site Engineer: "Pier 14 poured today."</div>
              <div>[!] Subcontractor: "Waiting on rebar delivery."</div>
              <div>[!] Result: 22-day project schedule drift undetected.</div>
            </div>
          </div>

          {/* Cognitive Engine Card */}
          <div
            style={{
              background: "rgba(10, 25, 28, 0.75)",
              border: "1px solid rgba(45, 212, 191, 0.4)",
              borderRadius: 16,
              padding: "32px 28px",
              position: "relative",
              overflow: "hidden",
              boxShadow: "0 0 30px rgba(13, 148, 136, 0.15)",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 20 }}>
              <span style={{ fontSize: 12, fontWeight: 800, color: "#2DD4BF", letterSpacing: "0.05em", textTransform: "uppercase" }}>
                Cognitive Engine • Autonomous Truth
              </span>
              <span style={{ fontSize: 11, color: "#2DD4BF", background: "rgba(45, 212, 191, 0.15)", padding: "4px 8px", borderRadius: 6 }}>
                ISO 21500 Controls
              </span>
            </div>
            <h3 style={{ fontSize: 22, fontWeight: 700, color: "#FFFFFF", margin: "0 0 16px" }}>
              Multi-Source Cross-Examination
            </h3>
            <ul style={{ listStyle: "none", padding: 0, margin: "0 0 24px", display: "flex", flexDirection: "column", gap: 14, color: "#E6EDF3", fontSize: 14 }}>
              <li style={{ display: "flex", gap: 10 }}>
                <span style={{ color: "#2DD4BF", fontWeight: 700 }}>✓</span>
                <span><strong>Multi-Modal Ingestion:</strong> Ingests drone point-clouds, WhatsApp site photos, and scanned challan PDFs simultaneously.</span>
              </li>
              <li style={{ display: "flex", gap: 10 }}>
                <span style={{ color: "#2DD4BF", fontWeight: 700 }}>✓</span>
                <span><strong>Semantic L5/L6 Alignment:</strong> Vector embeddings map unstructured site notes directly to official WBS Schedule Activity IDs.</span>
              </li>
              <li style={{ display: "flex", gap: 10 }}>
                <span style={{ color: "#2DD4BF", fontWeight: 700 }}>✓</span>
                <span><strong>Controlled Schedule Push:</strong> Nothing touches the baseline schedule without explicit planner sign-off and tamper-evident audit logs.</span>
              </li>
            </ul>
            <div style={{ background: "rgba(0,0,0,0.4)", borderRadius: 8, padding: "14px 16px", border: "1px solid rgba(45, 212, 191, 0.3)", fontFamily: "monospace", fontSize: 12, color: "#6EE7B7" }}>
              <div>[✓] Drone Point-Cloud: 78.4m³ concrete volume verified.</div>
              <div>[✓] Challan NLP: 80.0m³ batch plant dispatch matched.</div>
              <div>[✓] Auto-Resolved: 98.2% Confidence → Sent to Planner Gate.</div>
            </div>
          </div>

        </div>
      </section>

      {/* ============================================================ */}
      {/* 4. THE 4-STAGE AUTONOMOUS PIPELINE */}
      {/* ============================================================ */}
      <section id="pipeline" style={{ padding: "70px 24px 90px", background: "rgba(13, 17, 23, 0.5)", borderTop: "1px solid rgba(255, 255, 255, 0.05)", borderBottom: "1px solid rgba(255, 255, 255, 0.05)" }}>
        <div style={{ maxWidth: 1240, margin: "0 auto" }}>
          
          <div style={{ textAlign: "center", marginBottom: 50 }}>
            <span style={{ fontSize: 12, fontWeight: 700, color: "#2DD4BF", letterSpacing: "0.08em", textTransform: "uppercase" }}>
              Pipeline Mechanics
            </span>
            <h2 style={{ fontSize: 34, fontWeight: 800, color: "#FFFFFF", margin: "10px 0 12px" }}>
              The 4-Stage Reconciliation Flow
            </h2>
            <p style={{ color: "#8B949E", fontSize: 15, maxWidth: 600, margin: "0 auto" }}>
              How raw site evidence transforms into validated project intelligence in seconds.
            </p>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 20 }}>
            
            {[
              {
                step: "01",
                title: "Ingest & Normalize",
                tag: "MULTI-MODAL",
                desc: "Captures WhatsApp photos, drone orthomosaics, and supplier delivery challans. Normalizes disparate units (m, m³, tons, truckloads) into ISO standards.",
                color: "#2DD4BF",
              },
              {
                step: "02",
                title: "Semantic Match",
                tag: "L5/L6 WBS",
                desc: "Sentence transformer embeddings map colloquial descriptions ('poured south pier footing') to exact WBS Activity Codes (ACT-BR-014).",
                color: "#38BDF8",
              },
              {
                step: "03",
                title: "Cognitive Resolve",
                tag: "BAYESIAN WEIGHT",
                desc: "Identifies contradictions between drone survey vs contractor claims. Explains the exact mathematical reasoning behind every suggested reconciliation.",
                color: "#FBBF24",
              },
              {
                step: "04",
                title: "Controlled Push",
                tag: "PLANNER GATE",
                desc: "Project planner reviews AI-proposed updates with 1-click acceptance or calibrated override before writing back to Primavera P6 / MS Project.",
                color: "#A78BFA",
              },
            ].map((item, idx) => (
              <div
                key={idx}
                style={{
                  background: "rgba(17, 24, 39, 0.6)",
                  border: "1px solid rgba(255, 255, 255, 0.08)",
                  borderRadius: 14,
                  padding: "24px 20px",
                  position: "relative",
                  transition: "transform 0.2s, border-color 0.2s",
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.transform = "translateY(-4px)";
                  e.currentTarget.style.borderColor = item.color;
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.transform = "none";
                  e.currentTarget.style.borderColor = "rgba(255, 255, 255, 0.08)";
                }}
              >
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 14 }}>
                  <span style={{ fontSize: 24, fontWeight: 900, color: item.color, opacity: 0.9 }}>{item.step}</span>
                  <span style={{ fontSize: 10, fontWeight: 700, color: item.color, background: "rgba(255,255,255,0.06)", padding: "3px 8px", borderRadius: 4 }}>
                    {item.tag}
                  </span>
                </div>
                <h4 style={{ fontSize: 17, fontWeight: 700, color: "#FFFFFF", margin: "0 0 10px" }}>{item.title}</h4>
                <p style={{ fontSize: 13, color: "#8B949E", lineHeight: 1.5, margin: 0 }}>{item.desc}</p>
              </div>
            ))}

          </div>

        </div>
      </section>

      {/* ============================================================ */}
      {/* 5. INTERACTIVE CONFLICT STRESS-TEST SIMULATOR */}
      {/* ============================================================ */}
      <section id="simulator" style={{ padding: "90px 24px", maxWidth: 1240, margin: "0 auto" }}>
        
        <div style={{ textAlign: "center", marginBottom: 40 }}>
          <span style={{ fontSize: 12, fontWeight: 700, color: "#FBBF24", letterSpacing: "0.08em", textTransform: "uppercase" }}>
            Interactive Scenario Sandbox
          </span>
          <h2 style={{ fontSize: 34, fontWeight: 800, color: "#FFFFFF", margin: "10px 0 12px" }}>
            Conflict Stress-Test Simulator
          </h2>
          <p style={{ color: "#8B949E", fontSize: 15, maxWidth: 640, margin: "0 auto" }}>
            Experience how the Cognitive Engine cross-examines contradictory real-world evidence.
            Select a scenario below to watch the autonomous arbitration trace.
          </p>
        </div>

        {/* Scenario Selectors */}
        <div style={{ display: "flex", gap: 12, justifyContent: "center", marginBottom: 30, flexWrap: "wrap" }}>
          {scenarios.map((sc, i) => (
            <button
              key={i}
              onClick={() => setSelectedScenario(i)}
              style={{
                background: selectedScenario === i ? "rgba(13, 148, 136, 0.25)" : "rgba(255, 255, 255, 0.04)",
                border: selectedScenario === i ? "1px solid #2DD4BF" : "1px solid rgba(255, 255, 255, 0.1)",
                color: selectedScenario === i ? "#2DD4BF" : "#8B949E",
                padding: "10px 20px",
                borderRadius: 10,
                fontSize: 13,
                fontWeight: 600,
                cursor: "pointer",
                transition: "all 0.15s",
              }}
            >
              Scenario {i + 1}: {sc.title}
            </button>
          ))}
        </div>

        {/* Active Scenario Terminal View */}
        <div
          style={{
            background: "#0D1117",
            border: "1px solid rgba(45, 212, 191, 0.3)",
            borderRadius: 16,
            padding: "32px",
            boxShadow: "0 20px 50px rgba(0,0,0,0.5)",
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid rgba(255,255,255,0.08)", paddingBottom: 18, marginBottom: 24 }}>
            <div>
              <span style={{ fontSize: 11, fontWeight: 700, color: "#FBBF24", background: "rgba(251, 191, 36, 0.15)", padding: "3px 8px", borderRadius: 4 }}>
                {scenarios[selectedScenario].type}
              </span>
              <h3 style={{ fontSize: 20, fontWeight: 800, color: "#FFFFFF", margin: "8px 0 0" }}>
                {scenarios[selectedScenario].title}
              </h3>
            </div>
            <div style={{ textAlign: "right" }}>
              <div style={{ fontSize: 11, color: "#8B949E" }}>ARBITRATION CONFIDENCE</div>
              <div style={{ fontSize: 22, fontWeight: 900, color: "#2DD4BF" }}>
                {scenarios[selectedScenario].confidence}
              </div>
            </div>
          </div>

          <div style={{ display: "grid", gridTemplateColumns: "1.2fr 1fr", gap: 32 }}>
            <div>
              <h4 style={{ fontSize: 13, fontWeight: 700, color: "#8B949E", textTransform: "uppercase", letterSpacing: "0.04em", margin: "0 0 8px" }}>
                Contradictory Site Incident
              </h4>
              <p style={{ fontSize: 14, color: "#E6EDF3", lineHeight: 1.6, background: "rgba(255,255,255,0.03)", padding: "16px", borderRadius: 8, borderLeft: "3px solid #EF4444" }}>
                {scenarios[selectedScenario].description}
              </p>

              <h4 style={{ fontSize: 13, fontWeight: 700, color: "#8B949E", textTransform: "uppercase", letterSpacing: "0.04em", margin: "20px 0 8px" }}>
                AI Cross-Examination &amp; Reasoning
              </h4>
              <p style={{ fontSize: 14, color: "#6EE7B7", lineHeight: 1.6, background: "rgba(13, 148, 136, 0.08)", padding: "16px", borderRadius: 8, borderLeft: "3px solid #2DD4BF" }}>
                {scenarios[selectedScenario].resolution}
              </p>
            </div>

            <div style={{ display: "flex", flexDirection: "column", justifyContent: "space-between", background: "rgba(0,0,0,0.3)", borderRadius: 10, padding: "20px", border: "1px solid rgba(255,255,255,0.06)" }}>
              <div>
                <span style={{ fontSize: 11, fontWeight: 700, color: "#38BDF8", textTransform: "uppercase" }}>Recommended Action for Planner</span>
                <div style={{ fontSize: 15, fontWeight: 600, color: "#FFFFFF", marginTop: 8, lineHeight: 1.5 }}>
                  {scenarios[selectedScenario].recommendation}
                </div>
              </div>

              <div style={{ marginTop: 24, paddingTop: 18, borderTop: "1px solid rgba(255,255,255,0.08)" }}>
                <button
                  onClick={() => onEnterApp("conflicts")}
                  style={{
                    width: "100%",
                    background: "linear-gradient(135deg, #0D9488 0%, #0284C7 100%)",
                    border: "none",
                    color: "#FFFFFF",
                    padding: "12px",
                    borderRadius: 8,
                    fontWeight: 700,
                    fontSize: 13,
                    cursor: "pointer",
                  }}
                >
                  Open in Conflict Center →
                </button>
              </div>
            </div>
          </div>

        </div>

      </section>

      {/* ============================================================ */}
      {/* 6. CALL TO ACTION FOOTER */}
      {/* ============================================================ */}
      <footer
        id="specs"
        style={{
          borderTop: "1px solid rgba(255, 255, 255, 0.08)",
          background: "#05070A",
          padding: "60px 24px 40px",
          textAlign: "center",
        }}
      >
        <div style={{ maxWidth: 800, margin: "0 auto 40px" }}>
          <h3 style={{ fontSize: 28, fontWeight: 800, color: "#FFFFFF", margin: "0 0 14px" }}>
            Ready for Live Project Deployment?
          </h3>
          <p style={{ color: "#8B949E", fontSize: 15, lineHeight: 1.6, margin: "0 0 28px" }}>
            Experience full schedule reconciliation with live evidence feeds, semantic L5/L6 activity matching, and instant Primavera write-backs.
          </p>
          <div style={{ display: "flex", justifyContent: "center", gap: 14 }}>
            <button
              onClick={() => onEnterApp("reconciliation")}
              style={{
                background: "linear-gradient(135deg, #0D9488 0%, #0284C7 100%)",
                border: "none",
                color: "#FFFFFF",
                padding: "14px 32px",
                borderRadius: 10,
                fontSize: 15,
                fontWeight: 700,
                cursor: "pointer",
                boxShadow: "0 4px 20px rgba(13, 148, 136, 0.4)",
              }}
            >
              Enter Mission Control Now
            </button>
            <button
              onClick={() => onEnterApp("reviews")}
              style={{
                background: "rgba(255, 255, 255, 0.06)",
                border: "1px solid rgba(255, 255, 255, 0.15)",
                color: "#E6EDF3",
                padding: "14px 28px",
                borderRadius: 10,
                fontSize: 15,
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              Planner Review Center
            </button>
          </div>
        </div>

        <div style={{ borderTop: "1px solid rgba(255, 255, 255, 0.06)", paddingTop: 24, display: "flex", justifyContent: "space-between", alignItems: "center", maxWidth: 1240, margin: "0 auto", fontSize: 12, color: "#6E7681" }}>
          <div>CognitiveProgress Enterprise Controls • ISO 21500 Compliant</div>
          <div>FastAPI • PyTorch Embeddings • Gemini 2.0 • React • Vite</div>
          <div>Cognitive Progress Reconciliation Layer v2.0</div>
        </div>
      </footer>

    </div>
  );
}
