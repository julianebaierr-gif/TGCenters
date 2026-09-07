// TrendBlogo 15-Step Generator Wizard
document.addEventListener("DOMContentLoaded", () => {
  const wizardForm = document.getElementById("generator-form");
  if (!wizardForm) return;

  const keywordInput = document.getElementById("wizard-keyword");
  const secondaryKeywordsInput = document.getElementById("wizard-secondary-keywords");
  const categorySelect = document.getElementById("wizard-category");
  const toneSelect = document.getElementById("wizard-tone");
  const templateSelect = document.getElementById("wizard-template");
  const wordCountInput = document.getElementById("wizard-word-count");
  const publishModeSelect = document.getElementById("wizard-publish-mode");

  const btnAnalyze = document.getElementById("btn-wizard-analyze");
  const btnGenerateNow = document.getElementById("btn-wizard-generate");
  
  const stepConfig = document.getElementById("step-config");
  const stepAnalysis = document.getElementById("step-analysis");
  const stepProgress = document.getElementById("step-progress");
  const stepReview = document.getElementById("step-review");

  const intentBadge = document.getElementById("analysis-intent-badge");
  const templateBadge = document.getElementById("analysis-template-badge");
  const collisionAlert = document.getElementById("collision-alert");
  const collisionText = document.getElementById("collision-text");
  const outlineList = document.getElementById("analysis-outline-list");

  const progressStatusText = document.getElementById("progress-status-text");
  const progressBar = document.getElementById("generation-progress-bar");
  const progressPercent = document.getElementById("progress-percent");

  // Review screen elements
  const reviewTitle = document.getElementById("review-title");
  const reviewScore = document.getElementById("review-score");
  const reviewWordCount = document.getElementById("review-word-count");
  const reviewFeaturedImg = document.getElementById("review-featured-img");
  const reviewArticleLink = document.getElementById("review-article-link");
  const reviewEditLink = document.getElementById("review-edit-link");

  // OpenAI Key Elements inside Wizard
  const keyInput = document.getElementById("wizard-openai-key");
  const keyBadge = document.getElementById("wizard-key-badge");
  const keyBadgeText = document.getElementById("wizard-key-badge-text");
  const toggleKeyBtn = document.getElementById("toggle-wizard-key-btn");
  const testKeyBtn = document.getElementById("test-wizard-key-btn");
  const keyFeedback = document.getElementById("wizard-key-feedback");
  const keyFeedbackText = document.getElementById("wizard-key-feedback-text");
  const warningBanner = document.getElementById("api-key-warning-banner");

  function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return decodeURIComponent(parts.pop().split(';').shift());
    return '';
  }

  function updateKeyUI(active) {
    if (keyBadge) {
      keyBadge.className = `px-2.5 py-0.5 rounded-full text-[10px] font-mono font-bold inline-flex items-center space-x-1.5 ${active ? 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20' : 'bg-amber-500/10 text-amber-300 border border-amber-500/20'}`;
      if (keyBadgeText) keyBadgeText.textContent = active ? "Key Ready & Active" : "API Key Required";
    }
    if (warningBanner) {
      if (active) warningBanner.classList.add("hidden");
      else warningBanner.classList.remove("hidden");
    }
  }

  function showKeyFeedback(msg, success) {
    if (!keyFeedback || !keyFeedbackText) return;
    keyFeedback.className = `text-[11px] p-2 rounded-lg border flex items-center space-x-2 ${success ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300' : 'bg-rose-500/10 border-rose-500/30 text-rose-300'}`;
    keyFeedbackText.textContent = msg;
    keyFeedback.classList.remove("hidden");
  }

  // Restore stored key if input empty
  if (keyInput) {
    const stored = localStorage.getItem("trendblogo_openai_key") || getCookie("tb_openai_key");
    if (stored && !keyInput.value.trim()) {
      keyInput.value = stored;
    }
    if (keyInput.value.trim().startsWith("sk-")) {
      updateKeyUI(true);
    }

    if (toggleKeyBtn) {
      toggleKeyBtn.addEventListener("click", () => {
        const isPass = keyInput.type === "password";
        keyInput.type = isPass ? "text" : "password";
        const icon = document.getElementById("wizard-eye-icon");
        if (icon) icon.setAttribute("data-lucide", isPass ? "eye-off" : "eye");
        if (window.lucide) lucide.createIcons();
      });
    }

    if (testKeyBtn) {
      testKeyBtn.addEventListener("click", async () => {
        const key = keyInput.value.trim();
        if (!key || !key.startsWith("sk-")) {
          showKeyFeedback("Please enter a valid OpenAI API key starting with sk-...", false);
          return;
        }

        testKeyBtn.disabled = true;
        testKeyBtn.innerHTML = `<span class="animate-spin inline-block mr-1">&#9696;</span> Verifying...`;

        try {
          const res = await fetch("/admin/api/test-openai-key", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ api_key: key })
          });
          const d = await res.json();
          if (d.success) {
            localStorage.setItem("trendblogo_openai_key", key);
            document.cookie = `tb_openai_key=${encodeURIComponent(key)}; path=/; max-age=31536000; SameSite=Lax`;
            showKeyFeedback("OpenAI Key verified and saved successfully!", true);
            updateKeyUI(true);
          } else {
            showKeyFeedback(d.message || "Failed to verify key.", false);
          }
        } catch (e) {
          showKeyFeedback("Network error verifying key.", false);
        } finally {
          testKeyBtn.disabled = false;
          testKeyBtn.innerHTML = `<i data-lucide="plug-zap" class="w-3 h-3 mr-1"></i><span>Test / Save</span>`;
          if (window.lucide) lucide.createIcons();
        }
      });
    }
  }

  // 1. Analyze Step
  if (btnAnalyze) {
    btnAnalyze.addEventListener("click", async () => {
      const kw = keywordInput.value.trim();
      if (!kw) {
        alert("Please enter a primary keyword first.");
        keywordInput.focus();
        return;
      }

      btnAnalyze.disabled = true;
      btnAnalyze.innerHTML = `<span class="animate-spin inline-block mr-2">&#9696;</span> Analyzing Keyword...`;

      try {
        // Fetch Intent & Outline
        const resAnalyze = await fetch("/api/keywords/analyze", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ keyword: kw })
        });
        const analysisData = await resAnalyze.json();

        // Fetch Duplicate / Cannibalization Check
        const resDup = await fetch("/api/keywords/check-duplicate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ keyword: kw })
        });
        const dupData = await resDup.json();

        // Populate Analysis UI
        if (intentBadge) intentBadge.textContent = (analysisData.search_intent || "Informational").toUpperCase();
        if (templateBadge) templateBadge.textContent = (analysisData.template_type || "Ultimate Guide").replace("_", " ").toUpperCase();
        
        if (templateSelect) {
          templateSelect.value = analysisData.template_type || "ultimate_guide";
        }

        // Handle Cannibalization Warnings
        if (dupData.has_collision) {
          collisionAlert.classList.remove("hidden");
          collisionText.innerHTML = `<strong>Topical Overlap Alert:</strong> ${dupData.warnings.join(" ")}`;
        } else {
          collisionAlert.classList.add("hidden");
        }

        // Render Outline Preview (H2 to H5 + Semantic Keywords)
        if (outlineList && analysisData.outline) {
          outlineList.innerHTML = analysisData.outline.map((sec, i) => `
            <div class="p-3 bg-slate-900 border border-slate-800 rounded-xl text-xs space-y-1.5">
              <div class="font-bold text-indigo-300">H2: ${sec.h2}</div>
              ${sec.h3_list && sec.h3_list.length > 0 ? `
                <div class="pl-3 text-[11px] text-slate-300 space-y-0.5">
                  ${sec.h3_list.map(h3 => `<div>&bull; <strong>H3:</strong> ${h3}</div>`).join("")}
                </div>
              ` : ""}
              ${sec.h4_list && sec.h4_list.length > 0 ? `
                <div class="pl-6 text-[10px] text-slate-400 space-y-0.5">
                  ${sec.h4_list.map(h4 => `<div>&rsaquo; <strong>H4:</strong> ${h4}</div>`).join("")}
                </div>
              ` : ""}
              ${sec.h5_list && sec.h5_list.length > 0 ? `
                <div class="pl-9 text-[10px] text-slate-500 space-y-0.5">
                  ${sec.h5_list.map(h5 => `<div>- <em>H5:</em> ${h5}</div>`).join("")}
                </div>
              ` : ""}
              ${sec.semantic_keywords && sec.semantic_keywords.length > 0 ? `
                <div class="pt-1 flex flex-wrap gap-1">
                  ${sec.semantic_keywords.map(sk => `<span class="px-1.5 py-0.5 bg-indigo-950/60 border border-indigo-800/40 rounded text-[9px] text-indigo-300 font-mono">#${sk}</span>`).join("")}
                </div>
              ` : ""}
            </div>
          `).join("");
        }

        // Auto-Detect Category and update selector
        if (analysisData.suggested_category) {
          const suggestedCat = analysisData.suggested_category;
          const hint = document.getElementById("wizard-category-hint");
          if (hint) {
            hint.innerHTML = `<span class="text-emerald-400 font-bold">✨ Auto-Detected Category:</span> ${suggestedCat.name} (will automatically file under ${suggestedCat.name})`;
          }
          if (categorySelect) {
            let found = false;
            for (let i = 0; i < categorySelect.options.length; i++) {
              if (categorySelect.options[i].value == suggestedCat.id || categorySelect.options[i].text.trim().toLowerCase() === suggestedCat.name.toLowerCase()) {
                categorySelect.selectedIndex = i;
                found = true;
                break;
              }
            }
            if (!found) {
              const opt = document.createElement("option");
              opt.value = suggestedCat.id;
              opt.text = `${suggestedCat.name} (Auto-Created)`;
              opt.selected = true;
              categorySelect.appendChild(opt);
            }
          }
        }

        // Reveal Analysis Screen
        stepAnalysis.classList.remove("hidden");
        stepAnalysis.scrollIntoView({ behavior: 'smooth', block: 'start' });

      } catch (err) {
        alert("Failed to analyze keyword. Please try again.");
      } finally {
        btnAnalyze.disabled = false;
        btnAnalyze.innerHTML = `Analyze Keyword & Intent &rarr;`;
      }
    });
  }

  // 2. Generate Step
  if (btnGenerateNow) {
    btnGenerateNow.addEventListener("click", async () => {
      const kw = keywordInput.value.trim();
      if (!kw) return;

      const keyVal = (keyInput ? keyInput.value.trim() : "") 
                     || localStorage.getItem("trendblogo_openai_key") 
                     || getCookie("tb_openai_key") || "";

      if (!keyVal || keyVal.length < 8 || !keyVal.startsWith("sk-")) {
        alert("Please enter your OpenAI API Key (starts with sk-...) in the API Key box before generating.");
        stepAnalysis.classList.add("hidden");
        stepConfig.classList.remove("hidden");
        if (keyInput) {
          keyInput.focus();
          keyInput.scrollIntoView({ behavior: 'smooth', block: 'center' });
        }
        return;
      }

      // Save to localStorage & cookie immediately
      localStorage.setItem("trendblogo_openai_key", keyVal);
      document.cookie = `tb_openai_key=${encodeURIComponent(keyVal)}; path=/; max-age=31536000; SameSite=Lax`;

      stepConfig.classList.add("hidden");
      stepAnalysis.classList.add("hidden");
      stepProgress.classList.remove("hidden");

      const payload = {
        keyword: kw,
        secondary_keywords: secondaryKeywordsInput.value.trim(),
        category_id: (categorySelect && categorySelect.value && categorySelect.value !== "auto" && !isNaN(parseInt(categorySelect.value))) ? parseInt(categorySelect.value) : "auto",
        tone: toneSelect.value,
        template_type: templateSelect.value,
        target_word_count: parseInt(wordCountInput.value) || 1500,
        publish_mode: publishModeSelect.value,
        openai_api_key: keyVal
      };

      // Animate progress simulation while worker executes
      let curProgress = 15;
      const progressTimer = setInterval(() => {
        if (curProgress < 88) {
          curProgress += 4;
          progressBar.style.width = curProgress + "%";
          progressPercent.textContent = curProgress + "%";
          if (curProgress === 35) progressStatusText.textContent = "Synthesizing deep ChatGPT article & plain-text headings...";
          if (curProgress === 55) progressStatusText.textContent = "Injecting contextual internal and authoritative external links...";
          if (curProgress === 75) progressStatusText.textContent = "Generating 2 real-life photographs via OpenAI API...";
          if (curProgress === 85) progressStatusText.textContent = "Generating Schema.org JSON-LD & running quality audit...";
        }
      }, 400);

      try {
        const res = await fetch("/api/articles/generate", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });

        clearInterval(progressTimer);

        if (!res.ok) {
          const errData = await res.json();
          throw new Error(errData.detail || "Generation failed.");
        }

        const data = await res.json();

        // 100% Complete
        progressBar.style.width = "100%";
        progressPercent.textContent = "100%";
        progressStatusText.textContent = "Generation complete! Rendering review...";

        setTimeout(() => {
          stepProgress.classList.add("hidden");
          stepReview.classList.remove("hidden");

          reviewTitle.textContent = data.title;
          reviewScore.textContent = `${data.quality_score}/100`;
          reviewWordCount.textContent = `${data.word_count} words`;
          if (reviewFeaturedImg) reviewFeaturedImg.src = data.featured_image;
          if (reviewArticleLink) reviewArticleLink.href = data.url;
          if (reviewEditLink) reviewEditLink.href = `/admin/articles/${data.article_id}/edit`;
        }, 600);

      } catch (err) {
        clearInterval(progressTimer);
        alert("Generation Error: " + err.message);
        stepProgress.classList.add("hidden");
        stepConfig.classList.remove("hidden");
      }
    });
  }
});
