/**
 * SmartContract Manager - Contract Term & Renewal Live Controller
 * Handles model separation (auto-renewing vs. fixed term), quick pills,
 * target period snapping, and real-time cancellation preview.
 */

(function () {
  'use strict';

  function padZero(n) {
    return n < 10 ? '0' + n : '' + n;
  }

  function formatDate(d) {
    if (!d || isNaN(d.getTime())) return '-';
    return padZero(d.getDate()) + '.' + padZero(d.getMonth() + 1) + '.' + d.getFullYear();
  }

  function parseDateInput(val) {
    if (!val) return null;
    const parts = val.split('-');
    if (parts.length !== 3) return null;
    const y = parseInt(parts[0], 10);
    const m = parseInt(parts[1], 10) - 1;
    const d = parseInt(parts[2], 10);
    const dt = new Date(y, m, d);
    return isNaN(dt.getTime()) ? null : dt;
  }

  function addMonths(d, months) {
    const res = new Date(d.getTime());
    const expectedMonth = (res.getMonth() + months) % 12;
    res.setMonth(res.getMonth() + months);
    // If month overflowed (e.g. Feb 30), pin to last day of target month
    if (res.getMonth() !== (expectedMonth < 0 ? expectedMonth + 12 : expectedMonth)) {
      res.setDate(0);
    }
    return res;
  }

  function snapToTargetPeriod(dt, periodType) {
    if (!dt || !periodType || periodType === 'exact') return dt;
    const y = dt.getFullYear();
    const m = dt.getMonth(); // 0-indexed

    if (periodType === 'end_of_month') {
      return new Date(y, m + 1, 0); // Last day of month
    } else if (periodType === 'end_of_quarter') {
      const qEndMonth = Math.floor(m / 3) * 3 + 3; // 3, 6, 9, 12
      return new Date(y, qEndMonth, 0);
    } else if (periodType === 'end_of_year') {
      return new Date(y, 11, 31);
    }
    return dt;
  }

  function formatISODate(d) {
    if (!d || isNaN(d.getTime())) return '';
    return d.getFullYear() + '-' + padZero(d.getMonth() + 1) + '-' + padZero(d.getDate());
  }

  function subtractNotice(dt, amount, unit) {
    const res = new Date(dt.getTime());
    const amt = parseInt(amount, 10) || 0;
    if (amt <= 0) return res;

    if (unit === 'months') {
      return addMonths(res, -amt);
    } else if (unit === 'weeks') {
      res.setDate(res.getDate() - amt * 7);
      return res;
    } else {
      res.setDate(res.getDate() - amt);
      return res;
    }
  }

  function calculateNextDue(anchorDate, freq, asOf) {
    if (!anchorDate || isNaN(anchorDate.getTime())) return null;
    const a = new Date(anchorDate.getFullYear(), anchorDate.getMonth(), anchorDate.getDate());
    const ref = new Date(asOf.getFullYear(), asOf.getMonth(), asOf.getDate());

    if (freq === 'weekly' || freq === 'biweekly') {
      const stepDays = freq === 'weekly' ? 7 : 14;
      const diffDays = Math.floor((ref.getTime() - a.getTime()) / (1000 * 60 * 60 * 24));
      const stepIdx = Math.floor(diffDays / stepDays) - 1;
      let cand = new Date(a.getTime() + stepIdx * stepDays * 24 * 60 * 60 * 1000);
      while (cand < ref) {
        cand = new Date(cand.getTime() + stepDays * 24 * 60 * 60 * 1000);
      }
      return cand;
    } else {
      const stepMonths = freq === 'quarterly' ? 3 : (freq === 'yearly' ? 12 : 1);
      const monthDiff = (ref.getFullYear() - a.getFullYear()) * 12 + (ref.getMonth() - a.getMonth());
      let stepIdx = Math.floor(monthDiff / stepMonths) - 1;
      let cand = addMonths(a, stepIdx * stepMonths);
      while (cand < ref) {
        stepIdx += 1;
        cand = addMonths(a, stepIdx * stepMonths);
      }
      return cand;
    }
  }

  function initContractTermGroup(groupEl) {
    if (groupEl._contractTermInitialized) return;
    groupEl._contractTermInitialized = true;

    const radioMonthly = groupEl.querySelector('.term-mode-radio-monthly');
    const radioFixedCycle = groupEl.querySelector('.term-mode-radio-fixed-cycle');
    const radioNone = groupEl.querySelector('.term-mode-radio-none');

    const containerAuto = groupEl.querySelector('.term-mode-auto-container');
    const containerFixed = groupEl.querySelector('.term-mode-fixed-container');

    const inputStartDate = groupEl.querySelector('[name="start_date"]');
    const inputEndDate = groupEl.querySelector('[name="end_date"]');
    const inputBillingAnchor = groupEl.querySelector('[name="billing_anchor_date"]');
    const selectFrequency = groupEl.querySelector('[name="frequency"]');
    const nextBillingBadge = groupEl.querySelector('.next-billing-preview-badge');
    let previousStartDateVal = inputStartDate ? inputStartDate.value : '';

    const inputInitialTerm = groupEl.querySelector('[name="initial_term_months"]');
    const inputInitialTermEndDate = groupEl.querySelector('[name="initial_term_end_date"]');
    const selectRenewalType = groupEl.querySelector('[name="renewal_type"]');
    const inputRenewalPeriod = groupEl.querySelector('[name="renewal_period_months"]');
    const renewalPeriodWrapper = groupEl.querySelector('.renewal-period-wrapper');
    const inputNoticeAmt = groupEl.querySelector('[name="cancellation_notice_amount"]');
    const selectNoticeUnit = groupEl.querySelector('[name="cancellation_notice_unit"]');
    const selectTargetPeriod = groupEl.querySelector('[name="cancellation_target_period"]');
    const targetPeriodWrapper = groupEl.querySelector('.cancellation-target-wrapper');

    const previewAlert = groupEl.querySelector('.term-live-preview');
    const previewText = groupEl.querySelector('.term-live-preview-text');

    function getSelectedRenewalType() {
      if (radioMonthly && radioMonthly.checked) return 'monthly_rolling';
      if (radioFixedCycle && radioFixedCycle.checked) return 'fixed_period';
      if (radioNone && radioNone.checked) return 'none';
      return selectRenewalType ? selectRenewalType.value : 'monthly_rolling';
    }

    function updateModeUI() {
      const rType = getSelectedRenewalType();

      if (selectRenewalType) {
        selectRenewalType.value = rType;
      }

      if (rType === 'none') {
        if (containerAuto) containerAuto.classList.add('d-none');
        if (containerFixed) containerFixed.classList.remove('d-none');
        if (renewalPeriodWrapper) renewalPeriodWrapper.classList.add('d-none');
        if (targetPeriodWrapper) targetPeriodWrapper.classList.add('d-none');
        if (inputInitialTerm) inputInitialTerm.value = '0';
        if (inputInitialTermEndDate) inputInitialTermEndDate.value = '';
      } else {
        if (containerAuto) containerAuto.classList.remove('d-none');
        if (containerFixed) containerFixed.classList.add('d-none');
        if (inputEndDate) inputEndDate.value = '';
        if (targetPeriodWrapper) targetPeriodWrapper.classList.remove('d-none');

        if (rType === 'fixed_period') {
          if (renewalPeriodWrapper) renewalPeriodWrapper.classList.remove('d-none');
          if (inputRenewalPeriod && (!inputRenewalPeriod.value || inputRenewalPeriod.value === '1')) {
            inputRenewalPeriod.value = '12';
          }
        } else {
          if (renewalPeriodWrapper) renewalPeriodWrapper.classList.add('d-none');
          if (inputRenewalPeriod) inputRenewalPeriod.value = '1';
        }
      }

      updatePillsHighlight();
      updatePreview();
    }

    function updatePillsHighlight() {
      const endVal = inputInitialTermEndDate ? inputInitialTermEndDate.value : '';
      const currentMonths = inputInitialTerm ? (parseInt(inputInitialTerm.value, 10) || 0) : 0;

      groupEl.querySelectorAll('[data-set-months]').forEach(function (pill) {
        const val = parseInt(pill.getAttribute('data-set-months'), 10);
        let isActive = false;
        if (val === 0 && !endVal && currentMonths === 0) {
          isActive = true;
        } else if (val > 0 && currentMonths === val) {
          isActive = true;
        }

        if (isActive) {
          pill.classList.remove('btn-outline-secondary');
          pill.classList.add('btn-primary', 'active');
        } else {
          pill.classList.remove('btn-primary', 'active');
          pill.classList.add('btn-outline-secondary');
        }
      });
    }

    function updatePreview() {
      if (!previewAlert || !previewText) return;
      const rType = getSelectedRenewalType();

      if (rType !== 'none') {
        const startDateVal = inputStartDate ? inputStartDate.value : '';
        const start = parseDateInput(startDateVal) || new Date();
        const targetPeriod = selectTargetPeriod ? selectTargetPeriod.value : 'exact';
        const noticeAmt = inputNoticeAmt ? (parseInt(inputNoticeAmt.value, 10) || 0) : 0;
        const noticeUnit = selectNoticeUnit ? selectNoticeUnit.value : 'days';

        let initialEnd = null;
        if (inputInitialTermEndDate && inputInitialTermEndDate.value) {
          initialEnd = parseDateInput(inputInitialTermEndDate.value);
        } else {
          const minMonths = inputInitialTerm ? (parseInt(inputInitialTerm.value, 10) || 0) : 0;
          if (minMonths > 0) {
            initialEnd = addMonths(start, minMonths);
          }
        }

        if (initialEnd) {
          initialEnd = snapToTargetPeriod(initialEnd, targetPeriod);
        }

        let html = '<div class="d-flex flex-wrap align-items-center gap-3">';
        if (initialEnd && initialEnd > start) {
          const deadline = subtractNotice(initialEnd, noticeAmt, noticeUnit);
          html += '<div><span class="text-muted d-block" style="font-size: 0.72rem;">Mindestlaufzeit bis:</span><strong class="text-success"><i class="bi bi-calendar-check me-1"></i>' + formatDate(initialEnd) + '</strong></div>';
          if (noticeAmt > 0) {
            html += '<div><span class="text-muted d-block" style="font-size: 0.72rem;">Kündigungsfrist bis:</span><strong class="text-body"><i class="bi bi-hourglass-top me-1 text-warning"></i>' + formatDate(deadline) + '</strong></div>';
          }
        } else {
          html += '<div><span class="text-muted d-block" style="font-size: 0.72rem;">Laufzeit-Status:</span><span class="badge bg-info-subtle text-info border"><i class="bi bi-arrow-repeat me-1"></i>Keine Mindestbindung (sofort flexibel)</span></div>';
        }

        let renewalDesc = 'monatlich rollierend (§ 309 Nr. 9 BGB)';
        if (rType === 'fixed_period') {
          const step = inputRenewalPeriod ? (parseInt(inputRenewalPeriod.value, 10) || 12) : 12;
          renewalDesc = 'feste Verlängerung (+' + step + ' Monate)';
        }

        html += '<div><span class="text-muted d-block" style="font-size: 0.72rem;">Verlängerung:</span><span class="badge bg-secondary-subtle text-secondary border">' + renewalDesc + '</span></div>';
        html += '</div>';

        previewAlert.className = 'term-live-preview alert alert-success-subtle border border-success-subtle small py-2 px-3 mb-0';
        previewText.innerHTML = html;
      } else {
        const endDateVal = inputEndDate ? inputEndDate.value : '';
        const end = parseDateInput(endDateVal);
        if (!end) {
          previewAlert.className = 'term-live-preview alert alert-light border small py-2 px-3 mb-0';
          previewText.innerHTML = '<i class="bi bi-info-circle me-1 text-primary"></i>Bitte festes Vertragsende angeben.';
          return;
        }

        let html = '<div class="d-flex flex-wrap align-items-center gap-3">';
        html += '<div><span class="text-muted d-block" style="font-size: 0.72rem;">Vertragsende (automatisch):</span><strong class="text-danger"><i class="bi bi-calendar-x me-1"></i>' + formatDate(end) + '</strong></div>';
        html += '<div><span class="badge bg-danger-subtle text-danger border">Keine Verlängerung</span></div>';
        html += '</div>';

        previewAlert.className = 'term-live-preview alert alert-danger-subtle border border-danger-subtle small py-2 px-3 mb-0';
        previewText.innerHTML = html;
      }
    }

    // Attach event listeners for radios
    if (radioMonthly) radioMonthly.addEventListener('change', updateModeUI);
    if (radioFixedCycle) radioFixedCycle.addEventListener('change', updateModeUI);
    if (radioNone) radioNone.addEventListener('change', updateModeUI);

    // Quick pills for months
    groupEl.querySelectorAll('[data-set-months]').forEach(function (pill) {
      pill.addEventListener('click', function (e) {
        e.preventDefault();
        const m = parseInt(this.getAttribute('data-set-months'), 10);
        if (inputInitialTerm) {
          inputInitialTerm.value = m;
          inputInitialTerm.dispatchEvent(new Event('change', { bubbles: true }));
        }

        if (inputInitialTermEndDate) {
          if (m === 0) {
            inputInitialTermEndDate.value = '';
          } else {
            const today = new Date();
            const todayClean = new Date(today.getFullYear(), today.getMonth(), today.getDate());
            const startDateVal = inputStartDate ? inputStartDate.value : '';
            const start = parseDateInput(startDateVal) || todayClean;

            // Mindestvertragslaufzeit (initial term) is always calculated from contract start date
            const targetPeriod = selectTargetPeriod ? selectTargetPeriod.value : 'exact';
            let calculatedEnd = addMonths(start, m);
            calculatedEnd = snapToTargetPeriod(calculatedEnd, targetPeriod);
            inputInitialTermEndDate.value = formatISODate(calculatedEnd);
          }
        }

        updatePillsHighlight();
        updatePreview();
      });
    });

    // When user manually types a date into initial_term_end_date
    if (inputInitialTermEndDate) {
      inputInitialTermEndDate.addEventListener('input', function () {
        const endDt = parseDateInput(this.value);
        const today = new Date();
        const todayClean = new Date(today.getFullYear(), today.getMonth(), today.getDate());
        const startDt = parseDateInput(inputStartDate ? inputStartDate.value : '') || todayClean;
        if (endDt && endDt > startDt && inputInitialTerm) {
          let nextDay = new Date(endDt.getFullYear(), endDt.getMonth(), endDt.getDate() + 1);
          let diffMonths;
          if (nextDay.getDate() === startDt.getDate() || (startDt.getDate() === 1 && nextDay.getDate() === 1)) {
            diffMonths = (nextDay.getFullYear() - startDt.getFullYear()) * 12 + (nextDay.getMonth() - startDt.getMonth());
          } else {
            diffMonths = (endDt.getFullYear() - startDt.getFullYear()) * 12 + (endDt.getMonth() - startDt.getMonth());
          }
          inputInitialTerm.value = Math.max(0, diffMonths);
          inputInitialTerm.dispatchEvent(new Event('change', { bubbles: true }));
        } else if (!this.value && inputInitialTerm) {
          inputInitialTerm.value = 0;
          inputInitialTerm.dispatchEvent(new Event('change', { bubbles: true }));
        }
        updatePillsHighlight();
        updatePreview();
      });
    }

    function updateNextBillingPreview() {
      if (!nextBillingBadge) return;
      const anchorVal = (inputBillingAnchor && inputBillingAnchor.value) ? inputBillingAnchor.value : (inputStartDate ? inputStartDate.value : '');
      const anchorDt = parseDateInput(anchorVal);
      if (!anchorDt) {
        nextBillingBadge.classList.add('d-none');
        return;
      }

      const freq = selectFrequency ? selectFrequency.value : 'monthly';
      const now = new Date();
      const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
      const startDt = parseDateInput(inputStartDate ? inputStartDate.value : '');
      const asOf = (startDt && startDt > today) ? startDt : today;

      const nextDue = calculateNextDue(anchorDt, freq, asOf);
      if (nextDue) {
        nextBillingBadge.innerHTML = '<i class="bi bi-calendar-check me-1"></i>Nächste Fälligkeit: ' + formatDate(nextDue);
        nextBillingBadge.title = 'Nächste Fälligkeit: ' + formatDate(nextDue);
        nextBillingBadge.classList.remove('d-none');
      } else {
        nextBillingBadge.classList.add('d-none');
      }
    }

    if (inputStartDate) {
      inputStartDate.addEventListener('input', function () {
        if (inputBillingAnchor) {
          if (!inputBillingAnchor.value || inputBillingAnchor.value === previousStartDateVal) {
            inputBillingAnchor.value = this.value;
          }
        }
        previousStartDateVal = this.value;
        updateNextBillingPreview();
      });
      inputStartDate.addEventListener('change', function () {
        previousStartDateVal = this.value;
        updateNextBillingPreview();
      });
    }

    if (inputBillingAnchor) {
      inputBillingAnchor.addEventListener('input', updateNextBillingPreview);
      inputBillingAnchor.addEventListener('change', updateNextBillingPreview);
    }

    if (selectFrequency) {
      selectFrequency.addEventListener('change', updateNextBillingPreview);
    }

    const watchInputs = [
      inputStartDate,
      inputEndDate,
      inputInitialTerm,
      inputInitialTermEndDate,
      selectRenewalType,
      inputRenewalPeriod,
      inputNoticeAmt,
      selectNoticeUnit,
      selectTargetPeriod,
    ];

    watchInputs.forEach(function (inp) {
      if (inp) {
        inp.addEventListener('input', updatePreview);
        inp.addEventListener('change', function () {
          updatePillsHighlight();
          updatePreview();
        });
      }
    });

    // Initial setup
    updateModeUI();
    updateNextBillingPreview();
  }

  // Live preview controller for #extendContractModal
  function initExtendModal() {
    const modal = document.getElementById('extendContractModal');
    if (!modal || modal._extendInit) return;
    modal._extendInit = true;

    const radioMonths = modal.querySelectorAll('[name="extension_months_radio"]');
    const inputHiddenMonths = modal.querySelector('input[type="hidden"][name="extension_months"]');
    const selectMonths = modal.querySelector('select[name="extension_months"]');
    const selectMode = modal.querySelector('[name="extension_start_mode"]');
    const inputCustomDate = modal.querySelector('[name="custom_end_date"]');
    const inputCustomStartDate = modal.querySelector('[name="custom_start_date"]');
    const customDateWrapper = modal.querySelector('.custom-date-wrapper');
    const customStartDateWrapper = modal.querySelector('.custom-start-date-wrapper');
    const previewBox = modal.querySelector('.extend-live-preview');
    const submitBtn = modal.querySelector('button[type="submit"]');

    const baseCurrentEndStr = modal.getAttribute('data-current-end') || '';
    const currentEndDt = parseDateInput(baseCurrentEndStr);

    function updateExtendPreview() {
      if (!previewBox) return;
      let monthsChoice = '24';
      if (inputHiddenMonths) {
        monthsChoice = inputHiddenMonths.value || '24';
      } else if (selectMonths) {
        monthsChoice = selectMonths.value || '24';
      }
      const mode = selectMode ? selectMode.value : 'append';

      // Toggle custom start date wrapper
      if (mode === 'custom_date') {
        if (customStartDateWrapper) customStartDateWrapper.classList.remove('d-none');
        if (inputCustomStartDate) inputCustomStartDate.required = true;
      } else {
        if (customStartDateWrapper) customStartDateWrapper.classList.add('d-none');
        if (inputCustomStartDate) inputCustomStartDate.required = false;
      }

      // Toggle custom end date wrapper
      if (monthsChoice === 'custom') {
        if (customDateWrapper) customDateWrapper.classList.remove('d-none');
        if (inputCustomDate) inputCustomDate.required = true;
      } else {
        if (customDateWrapper) customDateWrapper.classList.add('d-none');
        if (inputCustomDate) inputCustomDate.required = false;
      }

      // Determine baseDt
      const today = new Date();
      let baseDt = today;
      let missingStartDate = false;

      if (mode === 'custom_date') {
        const parsedStart = parseDateInput(inputCustomStartDate ? inputCustomStartDate.value : '');
        if (parsedStart) {
          baseDt = parsedStart;
        } else {
          missingStartDate = true;
        }
      } else if (mode === 'append' && currentEndDt && currentEndDt > today) {
        baseDt = currentEndDt;
      }

      // Failsafe 1: If custom start date chosen but missing
      if (missingStartDate) {
        previewBox.className = 'extend-live-preview alert alert-warning small py-2 px-3 mb-0';
        previewBox.innerHTML = '<i class="bi bi-info-circle text-warning me-1"></i>Bitte individuelles Startdatum wählen.';
        if (submitBtn) submitBtn.disabled = true;
        return;
      }

      // Custom End Date Mode
      if (monthsChoice === 'custom') {
        const customDt = parseDateInput(inputCustomDate ? inputCustomDate.value : '');
        if (!customDt) {
          previewBox.className = 'extend-live-preview alert alert-info small py-2 px-3 mb-0';
          previewBox.innerHTML = '<i class="bi bi-info-circle text-muted me-1"></i>Bitte individuelles Enddatum wählen.';
          if (submitBtn) submitBtn.disabled = true;
          return;
        }

        // Failsafe 2: End date must be after baseDt
        if (customDt <= baseDt) {
          previewBox.className = 'extend-live-preview alert alert-danger small py-2 px-3 mb-0';
          previewBox.innerHTML = '<i class="bi bi-exclamation-triangle-fill text-danger me-1"></i><strong>Fehler:</strong> Das Mindestende muss nach dem Startdatum (' + formatDate(baseDt) + ') liegen!';
          if (submitBtn) submitBtn.disabled = true;
          return;
        }

        previewBox.className = 'extend-live-preview alert alert-success-subtle border border-success-subtle small py-2 px-3 mb-0';
        previewBox.innerHTML = '<div><span class="text-muted small d-block">Neues Mindestende (ab ' + formatDate(baseDt) + '):</span>' +
          '<strong class="text-success fs-6"><i class="bi bi-calendar-check me-1"></i>' + formatDate(customDt) + '</strong></div>';
        checkTiersValidityAndEnableSubmit();
        return;
      }

      // Fixed duration (e.g. 12, 24 months)
      const addM = parseInt(monthsChoice, 10) || 24;
      const newEnd = addMonths(baseDt, addM);

      previewBox.className = 'extend-live-preview alert alert-success-subtle border border-success-subtle small py-2 px-3 mb-0';
      let txt = '<div><span class="text-muted small d-block">Neues Mindestende (ab ' + formatDate(baseDt) + '):</span>';
      txt += '<strong class="text-success fs-6"><i class="bi bi-calendar-plus me-1"></i>' + formatDate(newEnd) + '</strong>';
      txt += ' <span class="badge bg-success-subtle text-success border ms-2">+' + addM + ' Monate</span></div>';

      previewBox.innerHTML = txt;
      checkTiersValidityAndEnableSubmit();
    }

    function checkTiersValidityAndEnableSubmit() {
      if (!submitBtn) return;
      const tiersCard = modal.querySelector('.price-tier-card');
      const jsonInput = modal.querySelector('.price-tiers-json-input');
      if (tiersCard && !tiersCard.classList.contains('d-none')) {
        if (!jsonInput || !jsonInput.value) {
          submitBtn.disabled = true;
          return;
        }
      }
      submitBtn.disabled = false;
    }

    modal._updateExtendPreview = updateExtendPreview;

    radioMonths.forEach(function (radio) {
      radio.addEventListener('change', function () {
        if (radio.checked) {
          if (inputHiddenMonths) inputHiddenMonths.value = radio.value;
          updateExtendPreview();
        }
      });
    });

    if (selectMonths) selectMonths.addEventListener('change', updateExtendPreview);
    if (selectMode) selectMode.addEventListener('change', updateExtendPreview);
    if (inputCustomDate) inputCustomDate.addEventListener('input', updateExtendPreview);
    if (inputCustomStartDate) inputCustomStartDate.addEventListener('input', updateExtendPreview);

    updateExtendPreview();
  }

  // Live controller for reusable price tier components (.price-tier-component)
  function initPriceTierControllers() {
    document.querySelectorAll('.price-tier-component').forEach(function (container) {
      if (container._tierInit) return;
      container._tierInit = true;

      const toggleBtn = container.querySelector('.toggle-price-tiers-btn');
      const closeBtn = container.querySelector('.close-price-tiers-btn');
      const card = container.querySelector('.price-tier-card');
      const rowsList = container.querySelector('.tier-rows-list');
      const addStepBtn = container.querySelector('.add-tier-btn');
      const summaryBadge = container.querySelector('.tier-summary-badge');
      const jsonInput = container.querySelector('.price-tiers-json-input');

      const form = container.closest('form') || container.closest('.modal');
      const singleAmountWrapper = form ? form.querySelector('.single-amount-wrapper') : null;
      const submitBtn = form ? form.querySelector('button[type="submit"]') : null;

      function getCurrency() {
        if (!form) return 'EUR';
        const curInput = form.querySelector('[name="currency"]');
        return curInput ? (curInput.value || 'EUR') : 'EUR';
      }

      function getBaseStartDate() {
        if (!form) return new Date();
        const startInput = form.querySelector('[name="start_date"]');
        if (startInput && startInput.value) {
          const d = parseDateInput(startInput.value);
          if (d) return d;
        }
        const modal = container.closest('#extendContractModal');
        if (modal) {
          const selectMode = modal.querySelector('[name="extension_start_mode"]');
          const mode = selectMode ? selectMode.value : 'append';
          if (mode === 'custom_date') {
            const customStartInput = modal.querySelector('[name="custom_start_date"]');
            if (customStartInput && customStartInput.value) {
              const d = parseDateInput(customStartInput.value);
              if (d) return d;
            }
          }
          const currentEndStr = modal.getAttribute('data-current-end');
          const currentEndDt = parseDateInput(currentEndStr);
          const today = new Date();
          if (mode === 'append' && currentEndDt && currentEndDt > today) {
            return currentEndDt;
          }
          return today;
        }
        return new Date();
      }

      function getInitialTermMonths() {
        if (!form) return 0;
        const termInput = form.querySelector('[name="initial_term_months"]');
        if (termInput && termInput.value !== undefined && termInput.value !== '') {
          const v = parseInt(termInput.value, 10);
          if (!isNaN(v)) return Math.max(0, v);
        }
        const extMonthsInput = form.querySelector('[name="extension_months"]');
        if (extMonthsInput && extMonthsInput.value && extMonthsInput.value !== 'custom') {
          const v = parseInt(extMonthsInput.value, 10);
          if (!isNaN(v)) return Math.max(0, v);
        }
        return 0;
      }

      function getBaseAmount() {
        if (!form) return '';
        const amtInput = form.querySelector('[name="amount"], [name="new_amount"]');
        return amtInput ? (amtInput.value || '') : '';
      }

      let tiers = [];

      function parseAmount(val) {
        if (val === undefined || val === null || val === '') return NaN;
        return parseFloat(String(val).replace(',', '.'));
      }

      function syncToForm() {
        if (card.classList.contains('d-none')) {
          jsonInput.value = '';
          return;
        }

        const validTiers = tiers
          .filter(function (t) {
            const num = parseAmount(t.amount);
            return !isNaN(num) && num >= 0;
          })
          .map(function (t, idx) {
            const isLast = idx === tiers.length - 1;
            return {
              months: isLast ? null : (parseInt(t.months, 10) || 1),
              amount: parseAmount(t.amount),
              note: t.note || (isLast ? 'Regulärer Folgepreis' : 'Rabattphase')
            };
          });

        const lastTier = tiers.length > 0 ? tiers[tiers.length - 1] : null;
        const lastTierNum = lastTier ? parseAmount(lastTier.amount) : NaN;
        const lastTierHasAmount = !isNaN(lastTierNum) && lastTierNum >= 0;

        if (validTiers.length >= 2 && lastTierHasAmount) {
          jsonInput.value = JSON.stringify(validTiers);
        } else {
          jsonInput.value = '';
        }

        updateSummaryBadge();

        const modal = container.closest('#extendContractModal');
        if (modal && modal._updateExtendPreview) {
          modal._updateExtendPreview();
        } else if (submitBtn) {
          if (!card.classList.contains('d-none') && !jsonInput.value) {
            submitBtn.disabled = true;
          } else {
            submitBtn.disabled = false;
          }
        }
      }

      function updateSummaryBadge() {
        if (!summaryBadge) return;
        const lastTier = tiers.length > 0 ? tiers[tiers.length - 1] : null;
        const lastTierNum = lastTier ? parseAmount(lastTier.amount) : NaN;
        const missingFolgepreis = isNaN(lastTierNum) || lastTierNum < 0;

        let totalMonths = 0;
        tiers.forEach(function (t, idx) {
          if (idx < tiers.length - 1) {
            totalMonths += (parseInt(t.months, 10) || 0);
          }
        });

        const expectedTerm = getInitialTermMonths();
        if (missingFolgepreis) {
          summaryBadge.className = 'tier-summary-badge badge bg-warning-subtle text-warning-emphasis border';
          summaryBadge.innerHTML = '<i class="bi bi-exclamation-circle me-1"></i>Bitte regulären Folgepreis eingeben';
        } else if (expectedTerm === 0) {
          summaryBadge.className = 'tier-summary-badge badge bg-info-subtle text-info-emphasis border';
          summaryBadge.innerHTML = '<i class="bi bi-tag me-1"></i>Rabattphase: ' + totalMonths + ' Monate (Vertrag ist monatlich flexibel)';
        } else if (totalMonths === expectedTerm) {
          summaryBadge.className = 'tier-summary-badge badge bg-success-subtle text-success border';
          summaryBadge.innerHTML = '<i class="bi bi-check-circle me-1"></i>Deckt Mindestlaufzeit exakt ab (' + totalMonths + ' Monate)';
        } else if (totalMonths < expectedTerm) {
          const diff = expectedTerm - totalMonths;
          summaryBadge.className = 'tier-summary-badge badge bg-warning-subtle text-warning-emphasis border';
          summaryBadge.innerHTML = '<i class="bi bi-hourglass-split me-1"></i>' + totalMonths + ' von ' + expectedTerm + ' Monaten verplant (noch ' + diff + ' M. offen)';
        } else {
          summaryBadge.className = 'tier-summary-badge badge bg-info-subtle text-info-emphasis border';
          summaryBadge.innerHTML = '<i class="bi bi-calendar-check me-1"></i>Laufzeit der Rabattphase: ' + totalMonths + ' Monate (Mindestlaufzeit: ' + expectedTerm + ' M.)';
        }
      }

      function renderTiers() {
        rowsList.innerHTML = '';
        const baseDt = getBaseStartDate();
        const cur = getCurrency();
        let runningStart = new Date(baseDt.getTime());

        let totalMonths = 0;

        tiers.forEach(function (tier, idx) {
          const isFirst = idx === 0;
          const isLast = idx === tiers.length - 1;

          let dateRangeText = '';
          if (isLast) {
            dateRangeText = '<i class="bi bi-calendar3 me-1"></i>ab ' + formatDate(runningStart);
          } else {
            const m = parseInt(tier.months, 10) || 0;
            totalMonths += m;
            const nextStart = addMonths(runningStart, m);
            const endDate = new Date(nextStart.getTime());
            endDate.setDate(endDate.getDate() - 1);
            dateRangeText = '<i class="bi bi-calendar-range me-1"></i>' + formatDate(runningStart) + ' – ' + formatDate(endDate);
            runningStart = nextStart;
          }

          const row = document.createElement('div');
          row.className = 'border rounded p-2 bg-body';

          let phaseBadgeHtml = '';
          let durationInputHtml = '';
          if (isFirst) {
            phaseBadgeHtml = '<span class="badge bg-primary text-white me-1">1. Phase</span> <span class="fw-semibold small">Rabatt / Aktionspreis</span>';
            durationInputHtml = '<div class="input-group input-group-sm">' +
              '<span class="input-group-text">für</span>' +
              '<input type="number" min="1" class="form-control tier-months-input" data-idx="' + idx + '" value="' + (tier.months || '') + '">' +
              '<span class="input-group-text">Monate</span>' +
            '</div>';
          } else if (isLast) {
            phaseBadgeHtml = '<span class="badge bg-secondary text-white me-1">Folgepreis</span> <span class="fw-semibold small">Regulär nach Rabattphase</span>';
            durationInputHtml = '<div class="form-control form-control-sm text-muted bg-body-tertiary text-center">&infin; dauerhaft fortlaufend</div>';
          } else {
            phaseBadgeHtml = '<span class="badge bg-info-subtle text-info-emphasis border me-1">' + (idx + 1) + '. Phase</span> <span class="fw-semibold small">Zwischenstufe</span>';
            durationInputHtml = '<div class="input-group input-group-sm">' +
              '<span class="input-group-text">für</span>' +
              '<input type="number" min="1" class="form-control tier-months-input" data-idx="' + idx + '" value="' + (tier.months || '') + '">' +
              '<span class="input-group-text">Monate</span>' +
            '</div>';
          }

          let removeBtnHtml = '';
          if (!isFirst && !isLast) {
            removeBtnHtml = '<button type="button" class="btn btn-sm btn-link text-danger p-0 tier-remove-btn ms-2" data-idx="' + idx + '" title="Stufe entfernen"><i class="bi bi-trash"></i></button>';
          }

          row.innerHTML = 
            '<div class="d-flex align-items-center justify-content-between mb-2 flex-wrap gap-1">' +
              '<div class="d-flex align-items-center">' + phaseBadgeHtml + '</div>' +
              '<div class="d-flex align-items-center gap-1">' +
                '<span class="badge bg-body-tertiary text-muted border py-1 px-2 small" style="font-size: 0.72rem;">' +
                  dateRangeText +
                '</span>' +
                removeBtnHtml +
              '</div>' +
            '</div>' +
            '<div class="row g-2 align-items-center">' +
              '<div class="col-12 col-sm-6">' + durationInputHtml + '</div>' +
              '<div class="col-12 col-sm-6">' +
                '<div class="input-group input-group-sm">' +
                  '<input type="number" step="0.01" min="0" placeholder="0.00" class="form-control tier-amount-input" data-idx="' + idx + '" value="' + (tier.amount || '') + '">' +
                  '<span class="input-group-text">' + cur + '</span>' +
                '</div>' +
              '</div>' +
            '</div>';

          rowsList.appendChild(row);
        });

        rowsList.querySelectorAll('.tier-months-input').forEach(function (inp) {
          inp.addEventListener('input', function () {
            const idx = parseInt(inp.getAttribute('data-idx'), 10);
            tiers[idx].months = inp.value;
            renderTiers();
            syncToForm();
          });
        });

        rowsList.querySelectorAll('.tier-amount-input').forEach(function (inp) {
          inp.addEventListener('input', function () {
            const idx = parseInt(inp.getAttribute('data-idx'), 10);
            tiers[idx].amount = inp.value;
            syncToForm();
          });
        });

        rowsList.querySelectorAll('.tier-remove-btn').forEach(function (btn) {
          btn.addEventListener('click', function () {
            const idx = parseInt(btn.getAttribute('data-idx'), 10);
            tiers.splice(idx, 1);
            renderTiers();
            syncToForm();
          });
        });

        updateSummaryBadge();
      }

      function openTiers() {
        card.classList.remove('d-none');
        toggleBtn.classList.add('d-none');
        if (singleAmountWrapper) {
          singleAmountWrapper.classList.add('d-none');
          const singleInput = singleAmountWrapper.querySelector('input');
          if (singleInput) singleInput.disabled = true;
        }
        if (tiers.length === 0) {
          const initialMonths = getInitialTermMonths();
          const defaultMonths = initialMonths > 0 ? initialMonths : 6;
          const baseAmt = getBaseAmount();
          tiers = [
            { months: defaultMonths, amount: baseAmt, note: 'Aktionspreis / Rabattphase' },
            { months: null, amount: '', note: 'Regulärer Folgepreis' }
          ];
        }
        renderTiers();
        syncToForm();
      }

      function closeTiers() {
        card.classList.add('d-none');
        toggleBtn.classList.remove('d-none');
        if (singleAmountWrapper) {
          singleAmountWrapper.classList.remove('d-none');
          const singleInput = singleAmountWrapper.querySelector('input');
          if (singleInput) {
            singleInput.disabled = false;
            if ((!singleInput.value || singleInput.value === '0.00') && tiers.length > 0 && tiers[0].amount) {
              singleInput.value = tiers[0].amount;
            }
          }
        }
        tiers = [];
        jsonInput.value = '';
        const modal = container.closest('#extendContractModal');
        if (modal && modal._updateExtendPreview) {
          modal._updateExtendPreview();
        } else if (submitBtn) {
          submitBtn.disabled = false;
        }
      }

      toggleBtn.addEventListener('click', openTiers);
      closeBtn.addEventListener('click', closeTiers);

      if (addStepBtn) {
        addStepBtn.addEventListener('click', function () {
          const lastIdx = tiers.length - 1;
          tiers.splice(lastIdx, 0, {
            months: 6,
            amount: '',
            note: 'Zwischenstufe'
          });
          renderTiers();
          syncToForm();
        });
      }

      if (form) {
        form.addEventListener('input', function (e) {
          if (e.target.name === 'amount' || e.target.name === 'new_amount') {
            if (!card.classList.contains('d-none') && tiers.length >= 1) {
              if (tiers[0].amount === '' || parseFloat(tiers[0].amount) === 0) {
                tiers[0].amount = e.target.value;
                renderTiers();
                syncToForm();
              }
            }
          } else if (e.target.name === 'start_date' || e.target.name === 'currency' || e.target.name === 'extension_start_mode' || e.target.name === 'custom_start_date') {
            if (!card.classList.contains('d-none')) {
              renderTiers();
              syncToForm();
            }
          }
        });
        form.addEventListener('change', function (e) {
          if (e.target.name === 'initial_term_months') {
            const newTerm = parseInt(e.target.value, 10) || 0;
            if (tiers.length === 2 && newTerm > 0) {
              tiers[0].months = newTerm;
            }
            if (!card.classList.contains('d-none')) {
              renderTiers();
              syncToForm();
            }
          } else if (e.target.name === 'start_date' || e.target.name === 'currency' || e.target.name === 'extension_start_mode' || e.target.name === 'custom_start_date') {
            if (!card.classList.contains('d-none')) {
              renderTiers();
              syncToForm();
            }
          }
        });
      }
    });
  }

  function initAll() {
    document.querySelectorAll('.contract-term-group').forEach(initContractTermGroup);
    initExtendModal();
    initPriceTierControllers();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initAll);
  } else {
    initAll();
  }

  document.addEventListener('shown.bs.modal', function () {
    initAll();
  });
})();

