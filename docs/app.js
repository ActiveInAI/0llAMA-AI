const itemGroups = {
  structureItems: [
    ["steelColumns", "钢柱", "主钢构件", "t", 0, 4800],
    ["steelBeams", "钢梁", "主钢构件", "t", 0, 4800],
    ["roofTruss", "屋架/桁架", "主钢构件", "t", 0, 5000],
    ["purlins", "檩条", "次钢结构", "t", 0, 4600],
    ["supports", "支撑/拉条/隅撑", "次钢结构", "t", 0, 4500],
    ["connectors", "连接件/节点板", "连接系统", "t", 0, 5200],
    ["highStrengthBolts", "高强螺栓", "连接系统", "套", 0, 18],
    ["antiCorrosion", "防腐喷涂", "表面处理", "㎡", 0, 22],
    ["fireCoating", "防火涂层", "表面处理", "㎡", 0, 38],
  ],
  enclosureItems: [
    ["roofPanels", "屋面系统", "屋面板/夹芯板", "㎡", 0, 135],
    ["roofInsulation", "屋面保温", "保温和防水层", "㎡", 0, 42],
    ["outerWall", "外墙系统", "外墙板", "㎡", 0, 128],
    ["innerWall", "内墙系统", "内墙/隔墙", "㎡", 0, 88],
    ["doorsWindows", "门窗系统", "卷帘门/铝窗/百叶", "㎡", 0, 420],
    ["flashing", "收边泛水", "包边/泛水/收口", "项", 0, 3000],
  ],
  componentItems: [
    ["stairs", "钢楼梯", "功能件", "套", 0, 7800],
    ["platforms", "平台/走道", "功能件", "㎡", 0, 360],
    ["railings", "栏杆/护栏", "功能件", "m", 0, 95],
    ["canopies", "雨棚", "功能件", "㎡", 0, 240],
    ["bathroomModules", "卫浴模块", "模块件", "套", 0, 12500],
    ["kitchenModules", "厨房模块", "模块件", "套", 0, 16800],
  ],
  mepItems: [
    ["airConditioners", "空调", "暖通设备", "套", 0, 3200],
    ["ventilation", "通风/排风", "暖通设备", "项", 0, 6800],
    ["lighting", "照明系统", "按面积", "㎡", 0, 35],
    ["powerDistribution", "配电系统", "配电箱/回路", "项", 0, 9800],
    ["plumbing", "给排水系统", "给排水", "项", 0, 8500],
    ["fireProtection", "消防基础配置", "消防", "项", 0, 12000],
  ],
  serviceItems: [
    ["projectManagement", "项目管理", "服务费", "项", 1, 8000],
    ["siteSupervision", "项目督导", "服务费", "项", 1, 6000],
    ["installation", "项目安装", "服务费", "项", 1, 20000],
    ["training", "安装培训", "服务费", "项", 1, 3000],
    ["storage", "仓储费", "按天计", "天", 0, 300],
    ["storageManagement", "仓储管理费", "服务费", "项", 1, 2000],
    ["logistics", "物流运输费", "按车次计", "车次", 0, 2500],
    ["warrantyService", "质保服务费", "服务费", "项", 1, 0],
  ],
};

const currency = new Intl.NumberFormat("zh-CN", {
  style: "currency",
  currency: "CNY",
  minimumFractionDigits: 2,
});

const form = document.getElementById("quoteForm");
const summaryOutput = document.getElementById("summaryOutput");
const buildingAreaInput = document.getElementById("buildingArea");
const copyBtn = document.getElementById("copyBtn");
const resetBtn = document.getElementById("resetBtn");

let discountMode = "rate";

function toNumber(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function formatCurrency(value) {
  return currency.format(value || 0);
}

function renderItems() {
  Object.entries(itemGroups).forEach(([containerId, items]) => {
    const container = document.getElementById(containerId);
    container.innerHTML = items
      .map(([key, title, note, unit, quantity, unitPrice]) => {
        return `
          <div class="table-row">
            <div class="table-row-name">
              <strong>${title}</strong>
              <small>${note}</small>
            </div>
            <div class="table-cell">
              <span class="mobile-label">单位</span>
              <span class="unit-chip">${unit}</span>
            </div>
            <label class="table-cell input-cell">
              <span class="mobile-label">工程量</span>
              <input
                data-role="qty"
                data-key="${key}"
                type="number"
                min="0"
                step="0.01"
                inputmode="decimal"
                value="${quantity}"
              />
            </label>
            <label class="table-cell input-cell">
              <span class="mobile-label">单价</span>
              <input
                data-role="price"
                data-key="${key}"
                type="number"
                min="0"
                step="0.01"
                inputmode="decimal"
                value="${unitPrice}"
              />
            </label>
            <div class="table-cell">
              <span class="mobile-label">小计</span>
              <span class="subtotal-chip" id="${key}Subtotal">${formatCurrency(0)}</span>
            </div>
          </div>
        `;
      })
      .join("");
  });
}

function collectItems(groupName) {
  return itemGroups[groupName].map(([key, title]) => {
    const qtyInput = form.querySelector(`[data-role="qty"][data-key="${key}"]`);
    const priceInput = form.querySelector(`[data-role="price"][data-key="${key}"]`);
    const quantity = toNumber(qtyInput?.value);
    const unitPrice = toNumber(priceInput?.value);
    const subtotal = quantity * unitPrice;
    const subtotalNode = document.getElementById(`${key}Subtotal`);

    if (subtotalNode) {
      subtotalNode.textContent = formatCurrency(subtotal);
    }

    return { key, title, quantity, unitPrice, subtotal };
  });
}

function sumSubtotals(items) {
  return items.reduce((total, item) => total + item.subtotal, 0);
}

function updateArea() {
  const length = toNumber(form.elements.length.value);
  const width = toNumber(form.elements.width.value);
  const floors = Math.max(1, toNumber(form.elements.floors.value));
  const buildingCount = Math.max(1, toNumber(form.elements.buildingCount.value));
  const area = length * width * floors * buildingCount;
  buildingAreaInput.value = area ? area.toFixed(2) : "0.00";
}

function updateSummary(data) {
  const {
    projectName,
    buildingType,
    useType,
    buildingArea,
    quotePrice,
    discountAmount,
    dealPrice,
    annualMaintenance,
    totalMaintenance,
    warrantyYears,
    visitFee,
  } = data;

  const summary = [
    `项目：${projectName || "未命名项目"}`,
    `建筑类型：${buildingType || "-"}`,
    `使用功能：${useType || "-"}`,
    `建筑面积：${buildingArea.toFixed(2)} ㎡`,
    "",
    `标准报价：${formatCurrency(quotePrice)}`,
    `折扣：${formatCurrency(discountAmount)}`,
    `成交价：${formatCurrency(dealPrice)}`,
    "",
    `质保年限：${warrantyYears} 年`,
    `年度维保费：${formatCurrency(annualMaintenance)}`,
    `总维保费：${formatCurrency(totalMaintenance)}`,
    `2年后上门费：${formatCurrency(visitFee)} / 次`,
  ].join("\n");

  summaryOutput.value = summary;
}

function calculate() {
  updateArea();

  const structureItems = collectItems("structureItems");
  const enclosureItems = collectItems("enclosureItems");
  const componentItems = collectItems("componentItems");
  const mepItems = collectItems("mepItems");
  const serviceItems = collectItems("serviceItems");

  const structureCost = sumSubtotals(structureItems);
  const enclosureCost = sumSubtotals(enclosureItems);
  const componentCost = sumSubtotals(componentItems);
  const mepCost = sumSubtotals(mepItems);
  const serviceCost = sumSubtotals(serviceItems);

  const materialCost = structureCost + enclosureCost + componentCost + mepCost;

  const materialMarkupRate = toNumber(form.elements.materialMarkupRate.value) / 100;
  const managementRate = toNumber(form.elements.managementRate.value) / 100;
  const profitRate = toNumber(form.elements.profitRate.value) / 100;
  const discountRate = toNumber(form.elements.discountRate.value) / 100;
  const manualDiscountAmount = toNumber(form.elements.manualDiscountAmount.value);
  const maintenanceRate = toNumber(form.elements.maintenanceRate.value) / 100;
  const warrantyYears = Math.max(0, toNumber(form.elements.warrantyYears.value));
  const visitFee = toNumber(form.elements.visitFee.value);

  const materialMarkup = materialCost * materialMarkupRate;
  const managementCost = (materialCost + materialMarkup + serviceCost) * managementRate;
  const profitValue = (materialCost + materialMarkup + serviceCost + managementCost) * profitRate;
  const quotePrice = materialCost + materialMarkup + serviceCost + managementCost + profitValue;

  let discountAmount = quotePrice * discountRate;

  if (discountMode === "amount") {
    discountAmount = Math.min(Math.max(0, manualDiscountAmount), quotePrice);
    const nextRate = quotePrice > 0 ? (discountAmount / quotePrice) * 100 : 0;
    form.elements.discountRate.value = nextRate.toFixed(2);
  } else {
    discountAmount = Math.min(Math.max(0, discountAmount), quotePrice);
    form.elements.manualDiscountAmount.value = discountAmount.toFixed(2);
  }

  const dealPrice = Math.max(0, quotePrice - discountAmount);
  const annualMaintenance = dealPrice * maintenanceRate;
  const totalMaintenance = annualMaintenance * warrantyYears;
  const buildingArea = toNumber(form.elements.buildingArea.value);

  const nodes = {
    materialCost: materialCost,
    materialMarkup: materialMarkup,
    serviceCost: serviceCost,
    managementCost: managementCost,
    profitValue: profitValue,
    quotePrice: quotePrice,
    quotePriceInline: quotePrice,
    discountValue: discountAmount,
    discountValueInline: discountAmount,
    dealPrice: dealPrice,
    dealPriceInline: dealPrice,
    annualMaintenance: annualMaintenance,
    totalMaintenance: totalMaintenance,
  };

  Object.entries(nodes).forEach(([id, value]) => {
    const node = document.getElementById(id);
    if (node) {
      node.textContent = formatCurrency(value);
    }
  });

  document.getElementById("warrantyYearsDisplay").textContent = `${warrantyYears} 年`;
  document.getElementById("visitFeeDisplay").textContent = `${formatCurrency(visitFee)} / 次`;

  updateSummary({
    projectName: form.elements.projectName.value.trim(),
    buildingType: form.elements.buildingType.value,
    useType: form.elements.useType.value.trim(),
    buildingArea,
    quotePrice,
    discountAmount,
    dealPrice,
    annualMaintenance,
    totalMaintenance,
    warrantyYears,
    visitFee,
  });
}

function resetForm() {
  form.reset();
  discountMode = "rate";
  renderItems();
  updateArea();
  calculate();
}

function registerEvents() {
  form.addEventListener("input", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLInputElement || target instanceof HTMLSelectElement)) {
      return;
    }

    if (target.name === "manualDiscountAmount") {
      discountMode = "amount";
    } else if (target.name === "discountRate") {
      discountMode = "rate";
    }

    calculate();
  });

  copyBtn.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(summaryOutput.value);
      copyBtn.textContent = "已复制";
      window.setTimeout(() => {
        copyBtn.textContent = "复制报价摘要";
      }, 1200);
    } catch (error) {
      copyBtn.textContent = "复制失败";
      window.setTimeout(() => {
        copyBtn.textContent = "复制报价摘要";
      }, 1200);
    }
  });

  resetBtn.addEventListener("click", () => {
    resetForm();
  });
}

renderItems();
registerEvents();
calculate();
