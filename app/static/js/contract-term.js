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
    const inputInitialTerm = groupEl.querySelector('[name="initial_term_months"]');
    const inputInitialTermEndDate = groupEl.querySelector('[name="initial_term_end_date"]');
    const selectRenewalType = groupEl.querySelector('[name="renewal_type"]');
    const inputRenewalPeriod = groupEl.querySelector('[name="renewal_period_months"]');
    const renewalPeriodWrapper = groupEl.querySelector('.renewal-period-wrapper');
    const inputNoticeAmt = groupEl.querySelector('[name="cancellation_notice_amount"]');
    const selectNoticeUnit = groupEl.querySelector('[name="cancellation_notice_unit"]');
    const selectTargetPeriod = groupEl.querySelector('[name="cancellation_target_period"]');

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
        if (inputInitialTerm) inputInitialTerm.value = '0';
        if (inputInitialTermEndDate) inputInitialTermEndDate.value = '';
      } else {
        if (containerAuto) containerAuto.classList.remove('d-none');
        if (containerFixed) containerFixed.classList.add('d-none');
        if (inputEndDate) inputEndDate.value = '';

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
        }

        if (inputInitialTermEndDate) {
          if (m === 0) {
            inputInitialTermEndDate.value = '';
          } else {
            const startDateVal = inputStartDate ? inputStartDate.value : '';
            const start = parseDateInput(startDateVal) || new Date();
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
        const startDt = parseDateInput(inputStartDate ? inputStartDate.value : '') || new Date();
        if (endDt && endDt > startDt && inputInitialTerm) {
          const diffMonths = (endDt.getFullYear() - startDt.getFullYear()) * 12 + (endDt.getMonth() - startDt.getMonth());
          inputInitialTerm.value = Math.max(0, diffMonths);
        } else if (!this.value && inputInitialTerm) {
          inputInitialTerm.value = 0;
        }
        updatePillsHighlight();
        updatePreview();
      });
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
  }

  // Live preview controller for #extendContractModal
  function initExtendModal() {
    const modal = document.getElementById('extendContractModal');
    if (!modal || modal._extendInit) return;
    modal._extendInit = true;

    const selectMonths = modal.querySelector('[name="extension_months"]');
    const selectMode = modal.querySelector('[name="extension_start_mode"]');
    const inputCustomDate = modal.querySelector('[name="custom_end_date"]');
    const customDateWrapper = modal.querySelector('.custom-date-wrapper');
    const previewBox = modal.querySelector('.extend-live-preview');

    const baseCurrentEndStr = modal.getAttribute('data-current-end') || '';
    const currentEndDt = parseDateInput(baseCurrentEndStr);

    function updateExtendPreview() {
      if (!previewBox) return;
      const monthsChoice = selectMonths ? selectMonths.value : '24';
      const mode = selectMode ? selectMode.value : 'append';

      if (monthsChoice === 'custom') {
        if (customDateWrapper) customDateWrapper.classList.remove('d-none');
        const customDt = parseDateInput(inputCustomDate ? inputCustomDate.value : '');
        if (customDt) {
          previewBox.innerHTML = '<i class="bi bi-arrow-repeat text-primary me-1"></i>Neues Mindestende: <strong>' + formatDate(customDt) + '</strong>';
        } else {
          previewBox.innerHTML = '<i class="bi bi-info-circle text-muted me-1"></i>Bitte individuelles Datum wählen.';
        }
        return;
      }

      if (customDateWrapper) customDateWrapper.classList.add('d-none');

      const today = new Date();
      let baseDt = today;
      if (mode === 'append' && currentEndDt && currentEndDt > today) {
        baseDt = currentEndDt;
      }

      const addM = parseInt(monthsChoice, 10) || 24;
      const newEnd = addMonths(baseDt, addM);

      let txt = '<div><span class="text-muted small d-block">Neues Mindestende:</span>';
      txt += '<strong class="text-success fs-6"><i class="bi bi-calendar-plus me-1"></i>' + formatDate(newEnd) + '</strong>';
      txt += ' <span class="badge bg-success-subtle text-success border ms-2">+' + addM + ' Monate</span></div>';

      previewBox.innerHTML = txt;
    }

    if (selectMonths) selectMonths.addEventListener('change', updateExtendPreview);
    if (selectMode) selectMode.addEventListener('change', updateExtendPreview);
    if (inputCustomDate) inputCustomDate.addEventListener('input', updateExtendPreview);

    updateExtendPreview();
  }

  function initAll() {
    document.querySelectorAll('.contract-term-group').forEach(initContractTermGroup);
    initExtendModal();
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
