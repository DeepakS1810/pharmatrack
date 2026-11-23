/**
 * PharmaTrack DW: Authentic 3D Multidimensional OLAP Hypercube Engine
 * Dual-Engine: High-Performance 3D WebGL (Three.js r128) + Accessible 2D Polyhedral Fallback
 * Features:
 * - True 3D WebGL rendering with perspective projection, lighting, depth buffer, and visible cube faces.
 * - Distinct, accessible medicine category colors with synchronized legend:
 *     * Antibiotics: #0d9488 (Teal)
 *     * Analgesics & Antipyretics: #2563eb (Blue)
 *     * Antidiabetic: #7c3aed (Purple)
 *     * Hormone Preparations: #ea580c (Amber)
 * - 3D labeled coordinate axes with directional arrows and billboarded text sprites:
 *     * X-Axis: Medicine Name (or Category)
 *     * Y-Axis: Time Period (Quarter, Year, Month)
 *     * Z-Axis: Geographic Region (State)
 * - Outer 12-edge 3D bounding wireframe cage rotating in 360°.
 * - Full mouse drag (left-click rotate, right-click/shift pan, scroll-wheel zoom) and touch gestures (swipe-rotate, pinch-zoom).
 * - Interactive 3D Raycasting: hover highlight (emissive gold #f59e0b) with floating tooltip and coordinate inspector.
 * - Auto-Rotate toggle with smooth continuous rotation.
 * - Keyboard shortcuts: Arrow keys (orbit), +/- (zoom), R (reset view), Space (auto-rotate).
 * - Clear empty state handling when no data matches active filter.
 * - Synchronized 2D accessible cross-tabulation pivot table alternative.
 * - Seamless fallback to 2D polyhedral engine if WebGL context is unavailable.
 */

(function() {
  'use strict';

  // State variables
  let canvas = null;
  let container = null;
  let renderer = null;
  let scene = null;
  let camera = null;
  let controls = null;
  let cubeGroup = null;
  let animFrameId = null;

  let cubeData = null;
  let voxelMeshes = [];
  let hoveredMesh = null;
  let raycaster = null;
  let mouse = { x: 0, y: 0 };
  let isMouseOverCanvas = false;
  let isAutoRotating = false;
  let is3DMode = true;
  let isInitialized = false;

  // Direct mouse & touch rotation state
  let isDragging = false;
  let previousMousePosition = { x: 0, y: 0 };
  let touchStartDistance = 0;

  // Category Color Palette
  const CATEGORY_COLORS = {
    'Antibiotics': 0x0d9488,
    'Analgesics & Antipyretics': 0x2563eb,
    'Antidiabetic': 0x7c3aed,
    'Hormone Preparations': 0xea580c,
    'Default': 0x0d9488
  };

  const DEFAULT_CAM_POS = { x: 260, y: 220, z: 300 };

  // =========================================================================
  // DETECT WEBGL SUPPORT
  // =========================================================================
  function isWebGLAvailable() {
    try {
      const c = document.createElement('canvas');
      return !!(window.WebGLRenderingContext && (c.getContext('webgl') || c.getContext('experimental-webgl')));
    } catch (e) {
      return false;
    }
  }

  // =========================================================================
  // INITIALIZATION ENTRY POINT
  // =========================================================================
  window.initOlapCube = function() {
    canvas = document.getElementById('olapCanvas');
    if (!canvas) return;
    container = canvas.parentElement;

    if (isInitialized && renderer) {
      onResize();
      if (cubeData) buildCubeMesh(cubeData);
      return;
    }

    if (window.THREE && isWebGLAvailable()) {
      try {
        initThreeEngine();
        is3DMode = true;
        isInitialized = true;
        if (cubeData) {
          buildCubeMesh(cubeData);
        }
        return;
      } catch (err) {
        console.warn("Three.js WebGL initialization encountered an error. Falling back to 2D Canvas engine:", err);
      }
    }

    console.info("Running in 2D High-DPI Polyhedral Canvas mode.");
    is3DMode = false;
    isInitialized = true;
    init2DCanvasFallback();
    if (cubeData && window.render2DCubeCanvas) {
      window.render2DCubeCanvas(cubeData);
    }
  };

  function initThreeEngine() {
    const w = Math.max(container ? container.clientWidth : 0, canvas.offsetWidth || 0, 800);
    const h = 480;

    // 1. WebGL Renderer
    if (!renderer) {
      renderer = new THREE.WebGLRenderer({
        canvas: canvas,
        antialias: true,
        alpha: false,
        powerPreference: "default"
      });
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
      renderer.setSize(w, h, true);
      renderer.setClearColor(0xf8fafc, 1.0);
    } else {
      renderer.setSize(w, h, true);
    }

    // 2. Scene
    scene = new THREE.Scene();

    // 3. Perspective Camera
    camera = new THREE.PerspectiveCamera(45, w / h, 1, 3000);
    camera.position.set(DEFAULT_CAM_POS.x, DEFAULT_CAM_POS.y, DEFAULT_CAM_POS.z);
    camera.lookAt(0, 0, 0);

    // 4. Optional OrbitControls if available
    if (window.THREE.OrbitControls) {
      try {
        controls = new THREE.OrbitControls(camera, renderer.domElement);
        controls.enableDamping = true;
        controls.dampingFactor = 0.06;
        controls.minDistance = 90;
        controls.maxDistance = 1200;
        controls.target.set(0, 0, 0);
        controls.autoRotate = false;
        controls.autoRotateSpeed = 2.0;
      } catch (e) {
        console.warn("OrbitControls init failed, using built-in mouse controller:", e);
        controls = null;
      }
    }

    // 5. Lighting: Ambient + Dual Directional Lights for Depth & Specular
    const ambientLight = new THREE.AmbientLight(0xffffff, 0.90);
    scene.add(ambientLight);

    const dirLight1 = new THREE.DirectionalLight(0xffffff, 0.75);
    dirLight1.position.set(300, 450, 350);
    scene.add(dirLight1);

    const dirLight2 = new THREE.DirectionalLight(0xffffff, 0.45);
    dirLight2.position.set(-250, -200, -250);
    scene.add(dirLight2);

    // 6. Raycasting Setup
    raycaster = new THREE.Raycaster();

    // 7. Event Listeners
    setupEventListeners();

    // 8. Start Animation Loop
    if (!animFrameId) {
      animate();
    }
  }

  // =========================================================================
  // ANIMATION / RENDER LOOP
  // =========================================================================
  function animate() {
    animFrameId = requestAnimationFrame(animate);

    if (controls) {
      controls.update();
    } else if (isAutoRotating && cubeGroup) {
      cubeGroup.rotation.y += 0.008;
    }

    // Raycast hover detection when cursor is over canvas
    if (isMouseOverCanvas && raycaster && camera && voxelMeshes.length > 0) {
      raycaster.setFromCamera(mouse, camera);
      const intersects = raycaster.intersectObjects(voxelMeshes, false);

      if (intersects.length > 0) {
        const hit = intersects[0].object;
        if (hoveredMesh !== hit) {
          unhighlightMesh(hoveredMesh);
          highlightMesh(hit);
          hoveredMesh = hit;
        }
      } else {
        if (hoveredMesh) {
          unhighlightMesh(hoveredMesh);
          hoveredMesh = null;
          hideTooltip();
        }
      }
    }

    if (renderer && scene && camera) {
      renderer.render(scene, camera);
    }
  }

  // =========================================================================
  // BUILD 3D VOXEL HYPERCUBE MESHES
  // =========================================================================
  function buildCubeMesh(data) {
    if (!scene) return;

    // Clear previous group
    if (cubeGroup) {
      scene.remove(cubeGroup);
      cubeGroup.traverse(child => {
        if (child.geometry) child.geometry.dispose();
        if (child.material) {
          if (Array.isArray(child.material)) child.material.forEach(m => m.dispose());
          else child.material.dispose();
        }
      });
    }

    voxelMeshes = [];
    hoveredMesh = null;
    hideTooltip();

    const emptyState = document.getElementById('cube-empty-state');
    if (!data || !data.cells || data.cells.length === 0 || data.empty) {
      if (emptyState) emptyState.style.display = 'block';
      if (canvas) canvas.style.opacity = '0.3';
      return;
    }

    if (emptyState) emptyState.style.display = 'none';
    if (canvas) canvas.style.opacity = '1.0';

    cubeGroup = new THREE.Group();

    const xLabels = data.x_labels || [];
    const yLabels = data.y_labels || [];
    const zLabels = data.z_labels || [];

    const nx = Math.max(xLabels.length, 1);
    const ny = Math.max(yLabels.length, 1);
    const nz = Math.max(zLabels.length, 1);

    const maxVal = Math.max(data.max_val || 1, 1);
    const minVal = data.min_val || 0;

    // Update Telemetry scale max
    const scaleMaxEl = document.getElementById('scale-max');
    if (scaleMaxEl) {
      scaleMaxEl.innerText = data.measure === 'avg_price'
        ? `₹${maxVal.toFixed(2)}`
        : (data.measure === 'total_sales' ? `₹${Math.round(maxVal).toLocaleString()}` : Math.round(maxVal).toLocaleString());
    }

    // Geometry layout sizing
    const voxelSize = 24;
    const spacing = 36;

    const halfX = ((nx - 1) * spacing) / 2;
    const halfY = ((ny - 1) * spacing) / 2;
    const halfZ = ((nz - 1) * spacing) / 2;

    const boxGeo = new THREE.BoxGeometry(voxelSize, voxelSize, voxelSize);
    const edgesGeo = new THREE.EdgesGeometry(boxGeo);
    const edgeMat = new THREE.LineBasicMaterial({ color: 0x0f172a, transparent: true, opacity: 0.45 });

    // Category mapping
    const categoryMap = data.category_map || {};

    xLabels.forEach((x, xi) => {
      yLabels.forEach((y, yi) => {
        zLabels.forEach((z, zi) => {
          const match = data.cells.find(c => c.x === x && c.y === y && c.z === z);
          const val = match ? match.v : 0;
          const cat = match ? (match.cat || categoryMap[x] || 'Antibiotics') : (categoryMap[x] || 'Antibiotics');

          // Normalized measure intensity
          const intensity = Math.min(1.0, Math.max(0.18, val / maxVal));

          // Base category color
          const catHex = CATEGORY_COLORS[cat] || CATEGORY_COLORS['Default'];

          // Material with depth shading and specular sheen
          const mat = new THREE.MeshStandardMaterial({
            color: catHex,
            roughness: 0.35,
            metalness: 0.15,
            transparent: true,
            opacity: val > 0 ? (0.65 + intensity * 0.35) : 0.20
          });

          const mesh = new THREE.Mesh(boxGeo, mat);
          mesh.position.set(
            xi * spacing - halfX,
            yi * spacing - halfY,
            zi * spacing - halfZ
          );

          // Dark line edge overlay for crisp voxel boundaries
          const wireframe = new THREE.LineSegments(edgesGeo, edgeMat);
          mesh.add(wireframe);

          // Store cell metadata for raycasting inspection
          mesh.userData = {
            x: x,
            y: y,
            z: z,
            val: val,
            cat: cat,
            color: catHex,
            origOpacity: mat.opacity
          };

          voxelMeshes.push(mesh);
          cubeGroup.add(mesh);
        });
      });
    });

    // 1. Outer 12-Edge 3D Bounding Wireframe Cage
    const cageWidth = nx * spacing + 12;
    const cageHeight = ny * spacing + 12;
    const cageDepth = nz * spacing + 12;
    const cageGeo = new THREE.BoxGeometry(cageWidth, cageHeight, cageDepth);
    const cageEdges = new THREE.EdgesGeometry(cageGeo);
    const cageMat = new THREE.LineBasicMaterial({
      color: 0x94a3b8,
      transparent: true,
      opacity: 0.60
    });
    const cage = new THREE.LineSegments(cageEdges, cageMat);
    cubeGroup.add(cage);

    // 2. 3D Coordinate Axes with Directional Arrows & Billboarded Text Sprites
    const axisOrigin = {
      x: -halfX - 24,
      y: -halfY - 24,
      z: -halfZ - 24
    };

    const axisLength = Math.max(cageWidth, cageHeight, cageDepth) * 0.9;

    const dimXEl = document.getElementById('dim-x-select');
    const dimYEl = document.getElementById('dim-y-select');
    const dimZEl = document.getElementById('dim-z-select');
    const dimXLabel = (dimXEl && dimXEl.selectedIndex >= 0 && dimXEl.options[dimXEl.selectedIndex])
      ? dimXEl.options[dimXEl.selectedIndex].text.split(' ')[0] : 'Medicine';
    const dimYLabel = (dimYEl && dimYEl.selectedIndex >= 0 && dimYEl.options[dimYEl.selectedIndex])
      ? dimYEl.options[dimYEl.selectedIndex].text.split(' ')[0] : 'Time';
    const dimZLabel = (dimZEl && dimZEl.selectedIndex >= 0 && dimZEl.options[dimZEl.selectedIndex])
      ? dimZEl.options[dimZEl.selectedIndex].text.split(' ')[0] : 'Region';

    // X-Axis Arrow (Teal) -> Medicine Name / Category
    const arrowX = new THREE.ArrowHelper(
      new THREE.Vector3(1, 0, 0),
      new THREE.Vector3(axisOrigin.x, axisOrigin.y, axisOrigin.z),
      axisLength + 36,
      0x0d9488,
      16,
      9
    );
    cubeGroup.add(arrowX);
    const labelSpriteX = createTextSprite(`X: ${dimXLabel}`, '#0d9488');
    labelSpriteX.position.set(axisOrigin.x + axisLength + 50, axisOrigin.y, axisOrigin.z);
    cubeGroup.add(labelSpriteX);

    // Y-Axis Arrow (Blue) -> Time / Period
    const arrowY = new THREE.ArrowHelper(
      new THREE.Vector3(0, 1, 0),
      new THREE.Vector3(axisOrigin.x, axisOrigin.y, axisOrigin.z),
      axisLength + 36,
      0x2563eb,
      16,
      9
    );
    cubeGroup.add(arrowY);
    const labelSpriteY = createTextSprite(`Y: ${dimYLabel}`, '#2563eb');
    labelSpriteY.position.set(axisOrigin.x, axisOrigin.y + axisLength + 50, axisOrigin.z);
    cubeGroup.add(labelSpriteY);

    // Z-Axis Arrow (Purple) -> Region / Geography
    const arrowZ = new THREE.ArrowHelper(
      new THREE.Vector3(0, 0, 1),
      new THREE.Vector3(axisOrigin.x, axisOrigin.y, axisOrigin.z),
      axisLength + 36,
      0x7c3aed,
      16,
      9
    );
    cubeGroup.add(arrowZ);
    const labelSpriteZ = createTextSprite(`Z: ${dimZLabel}`, '#7c3aed');
    labelSpriteZ.position.set(axisOrigin.x, axisOrigin.y, axisOrigin.z + axisLength + 50);
    cubeGroup.add(labelSpriteZ);

    scene.add(cubeGroup);

    // Render immediately so user sees the updated 3D cube
    if (renderer && scene && camera) {
      renderer.render(scene, camera);
    }
  }

  // =========================================================================
  // TEXT SPRITE HELPER (3D Crisp Billboarded Canvas Text)
  // =========================================================================
  function createTextSprite(text, colorHex) {
    try {
      const c = document.createElement('canvas');
      c.width = 256;
      c.height = 72;
      const context = c.getContext('2d');
      if (!context) return new THREE.Group();
      context.fillStyle = colorHex;
      context.font = 'bold 26px system-ui, sans-serif';
      context.textAlign = 'center';
      context.textBaseline = 'middle';
      context.fillText(text, 128, 36);

      const texture = new THREE.CanvasTexture(c);
      const mat = new THREE.SpriteMaterial({ map: texture, transparent: true });
      const sprite = new THREE.Sprite(mat);
      sprite.scale.set(70, 20, 1);
      return sprite;
    } catch (e) {
      console.warn("Failed creating text sprite:", e);
      return new THREE.Group();
    }
  }

  // =========================================================================
  // HOVER & CLICK HIGHLIGHT (RAYCASTING)
  // =========================================================================
  function highlightMesh(mesh) {
    if (!mesh || !mesh.material) return;
    mesh.material.emissive = new THREE.Color(0xf59e0b); // Golden amber glow
    mesh.material.emissiveIntensity = 0.55;
    mesh.scale.set(1.15, 1.15, 1.15);

    if (canvas) canvas.style.cursor = 'pointer';

    showTooltip(mesh.userData);
    updateInspectorCard(mesh.userData);
  }

  function unhighlightMesh(mesh) {
    if (!mesh || !mesh.material) return;
    mesh.material.emissive = new THREE.Color(0x000000);
    mesh.material.emissiveIntensity = 0.0;
    mesh.scale.set(1.0, 1.0, 1.0);

    if (canvas) canvas.style.cursor = 'grab';
  }

  function showTooltip(data) {
    const tt = document.getElementById('cube-tooltip');
    if (!tt || !canvas) return;

    const rect = canvas.getBoundingClientRect();
    const clientX = ((mouse.x + 1) / 2) * rect.width + rect.left;
    const clientY = ((-mouse.y + 1) / 2) * rect.height + rect.top;

    tt.style.left = (clientX - rect.left + 16) + 'px';
    tt.style.top = (clientY - rect.top - 28) + 'px';
    tt.style.display = 'block';

    const measureName = (cubeData && cubeData.measure_label) ? cubeData.measure_label : 'Units Sold';
    const isCurrency = (cubeData && cubeData.measure_unit === '₹');
    const formattedVal = isCurrency
      ? `₹${Number(data.val).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
      : Math.round(Number(data.val)).toLocaleString();

    tt.innerHTML = `
      <div style="font-weight: 700; color: #0d9488; font-size: 13px; margin-bottom: 2px;">${data.x}</div>
      <div style="font-size: 11.5px; color: #475569; line-height: 1.45;">
        • Category: <strong style="color: #0f172a;">${data.cat || 'Pharmaceutical'}</strong><br>
        • Period (Y): <strong style="color: #2563eb;">${data.y}</strong><br>
        • Region (Z): <strong style="color: #7c3aed;">${data.z}</strong><br>
        • ${measureName}: <strong style="color: #0f172a; font-size: 12.5px;">${formattedVal}</strong>
      </div>
    `;
  }

  function hideTooltip() {
    const tt = document.getElementById('cube-tooltip');
    if (tt) tt.style.display = 'none';
  }

  function updateInspectorCard(data) {
    const insp = document.getElementById('inspector-text');
    if (!insp) return;

    const measureName = (cubeData && cubeData.measure_label) ? cubeData.measure_label : 'Units Sold (Quantity)';
    const isCurrency = (cubeData && cubeData.measure_unit === '₹');
    const formattedVal = isCurrency
      ? `₹${Number(data.val).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
      : Math.round(Number(data.val)).toLocaleString();

    insp.innerHTML = `
      <strong>Selected Voxel Coordinates:</strong><br>
      • Dimension X (Attribute): <strong style="color: #0d9488;">${data.x}</strong> (${data.cat || 'Pharmaceutical'})<br>
      • Dimension Y (Period / Time): <strong style="color: #2563eb;">${data.y}</strong><br>
      • Dimension Z (Geography / Region): <strong style="color: #7c3aed;">${data.z}</strong><br>
      • Aggregated Measure (${measureName}): <strong style="color: #0f172a; font-size: 14px;">${formattedVal}</strong>
    `;
  }

  // =========================================================================
  // EVENT LISTENERS & DIRECT MOUSE / TOUCH CONTROLS
  // =========================================================================
  function setupEventListeners() {
    if (!canvas) return;

    canvas.addEventListener('mousemove', (e) => {
      const rect = canvas.getBoundingClientRect();
      mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
      mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
      isMouseOverCanvas = true;

      // Direct drag rotation fallback if OrbitControls is absent
      if (isDragging && !controls && cubeGroup) {
        const deltaMove = {
          x: e.clientX - previousMousePosition.x,
          y: e.clientY - previousMousePosition.y
        };
        cubeGroup.rotation.y += deltaMove.x * 0.008;
        cubeGroup.rotation.x += deltaMove.y * 0.008;
        if (renderer && scene && camera) renderer.render(scene, camera);
      }
      previousMousePosition = { x: e.clientX, y: e.clientY };
    });

    canvas.addEventListener('mousedown', (e) => {
      isDragging = true;
      previousMousePosition = { x: e.clientX, y: e.clientY };
    });

    window.addEventListener('mouseup', () => {
      isDragging = false;
    });

    canvas.addEventListener('wheel', (e) => {
      if (!controls && camera) {
        const factor = e.deltaY > 0 ? 1.08 : 0.92;
        window.zoomCube(factor);
        e.preventDefault();
      }
    }, { passive: false });

    // Touch events for mobile/tablet
    canvas.addEventListener('touchstart', (e) => {
      if (e.touches.length === 1) {
        isDragging = true;
        previousMousePosition = { x: e.touches[0].clientX, y: e.touches[0].clientY };
      } else if (e.touches.length === 2) {
        touchStartDistance = Math.hypot(
          e.touches[0].clientX - e.touches[1].clientX,
          e.touches[0].clientY - e.touches[1].clientY
        );
      }
    }, { passive: true });

    canvas.addEventListener('touchmove', (e) => {
      if (e.touches.length === 1 && isDragging && !controls && cubeGroup) {
        const deltaX = e.touches[0].clientX - previousMousePosition.x;
        const deltaY = e.touches[0].clientY - previousMousePosition.y;
        cubeGroup.rotation.y += deltaX * 0.008;
        cubeGroup.rotation.x += deltaY * 0.008;
        previousMousePosition = { x: e.touches[0].clientX, y: e.touches[0].clientY };
        if (renderer && scene && camera) renderer.render(scene, camera);
      } else if (e.touches.length === 2 && camera) {
        const dist = Math.hypot(
          e.touches[0].clientX - e.touches[1].clientX,
          e.touches[0].clientY - e.touches[1].clientY
        );
        if (touchStartDistance > 0) {
          const factor = touchStartDistance / dist;
          window.zoomCube(factor > 1 ? 1.03 : 0.97);
        }
        touchStartDistance = dist;
      }
    }, { passive: true });

    canvas.addEventListener('touchend', () => {
      isDragging = false;
      touchStartDistance = 0;
    });

    canvas.addEventListener('mouseenter', () => {
      isMouseOverCanvas = true;
      if (canvas) canvas.style.cursor = 'grab';
    });

    canvas.addEventListener('mouseleave', () => {
      isMouseOverCanvas = false;
      if (hoveredMesh) {
        unhighlightMesh(hoveredMesh);
        hoveredMesh = null;
      }
      hideTooltip();
    });

    canvas.addEventListener('click', () => {
      if (hoveredMesh) {
        updateInspectorCard(hoveredMesh.userData);
        const origColor = hoveredMesh.material.color.clone();
        hoveredMesh.material.color.setHex(0xf59e0b);
        setTimeout(() => {
          if (hoveredMesh) hoveredMesh.material.color.copy(origColor);
        }, 150);
      }
    });

    // Keyboard navigation controls
    window.addEventListener('keydown', (e) => {
      if (!isMouseOverCanvas && document.activeElement && (document.activeElement.tagName === 'INPUT' || document.activeElement.tagName === 'SELECT')) return;

      if (e.key === 'r' || e.key === 'R') {
        window.resetCubeView();
      } else if (e.key === ' ' && isMouseOverCanvas) {
        window.toggleAutoRotate();
        e.preventDefault();
      } else if (e.key === '+' || e.key === '=') {
        window.zoomCube(0.85);
        e.preventDefault();
      } else if (e.key === '-' || e.key === '_') {
        window.zoomCube(1.15);
        e.preventDefault();
      } else if (e.key === 'ArrowLeft') {
        window.rotateCube(-15, 0);
        e.preventDefault();
      } else if (e.key === 'ArrowRight') {
        window.rotateCube(15, 0);
        e.preventDefault();
      } else if (e.key === 'ArrowUp') {
        window.rotateCube(0, -15);
        e.preventDefault();
      } else if (e.key === 'ArrowDown') {
        window.rotateCube(0, 15);
        e.preventDefault();
      }
    });

    window.addEventListener('resize', onResize);
    if (window.ResizeObserver && container) {
      new ResizeObserver(onResize).observe(container);
    }
  }

  function onResize() {
    if (!renderer || !camera || !container) return;
    const w = Math.max(container.clientWidth || 0, canvas.parentElement ? canvas.parentElement.clientWidth : 0, 800);
    const h = 480;
    if (w <= 0) return;
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    renderer.setSize(w, h, true);
    if (renderer && scene && camera) {
      renderer.render(scene, camera);
    }
  }
  window.resizeOlapCanvas = onResize;

  // =========================================================================
  // PUBLIC CONTROLS API
  // =========================================================================
  window.renderCubeCanvas = function(data) {
    if (!data) return;
    cubeData = data;

    if (!isInitialized) {
      window.initOlapCube();
    }

    if (is3DMode) {
      if (renderer) {
        buildCubeMesh(data);
      }
    } else {
      if (window.render2DCubeCanvas) {
        window.render2DCubeCanvas(data);
      }
    }
  };

  window.rotateCube = function(deltaXDeg, deltaYDeg) {
    const angleX = (deltaXDeg * Math.PI) / 180;
    const angleY = (deltaYDeg * Math.PI) / 180;

    if (cubeGroup) {
      cubeGroup.rotation.y += angleX;
      cubeGroup.rotation.x += angleY;
    }

    if (controls) {
      controls.update();
    }

    if (renderer && scene && camera) {
      renderer.render(scene, camera);
    }
  };

  window.zoomCube = function(factor) {
    if (camera) {
      camera.position.multiplyScalar(factor);
      const dist = camera.position.length();
      if (dist < 80) camera.position.setLength(80);
      if (dist > 1400) camera.position.setLength(1400);

      if (controls) {
        controls.update();
      }
      if (renderer && scene && camera) {
        renderer.render(scene, camera);
      }
    }
  };

  window.resetCubeView = function() {
    if (camera) {
      camera.position.set(DEFAULT_CAM_POS.x, DEFAULT_CAM_POS.y, DEFAULT_CAM_POS.z);
      camera.lookAt(0, 0, 0);
    }
    if (cubeGroup) {
      cubeGroup.rotation.set(0, 0, 0);
    }
    if (controls) {
      controls.target.set(0, 0, 0);
      controls.update();
    }
    if (renderer && scene && camera) {
      renderer.render(scene, camera);
    }
  };

  window.toggleAutoRotate = function() {
    isAutoRotating = !isAutoRotating;
    if (controls) {
      controls.autoRotate = isAutoRotating;
    }
    const btn = document.getElementById('btn-auto-rotate');
    if (btn) {
      if (isAutoRotating) {
        btn.innerHTML = '⏸ Pause Rotate';
        btn.classList.add('active');
        btn.style.background = '#0d9488';
        btn.style.color = '#ffffff';
        btn.style.borderColor = '#0f766e';
      } else {
        btn.innerHTML = '▶ Auto-Rotate';
        btn.classList.remove('active');
        btn.style.background = '';
        btn.style.color = '';
        btn.style.borderColor = '';
      }
    }
  };

  // =========================================================================
  // 2D HIGH-DPI POLYHEDRAL CANVAS ENGINE (Fallback Mode)
  // =========================================================================
  function init2DCanvasFallback() {
    if (!canvas) return;

    // If canvas was previously used for WebGL context, replace with clean clone for 2D
    let ctx = canvas.getContext('2d');
    if (!ctx) {
      const clone = canvas.cloneNode(true);
      canvas.parentNode.replaceChild(clone, canvas);
      canvas = clone;
      ctx = canvas.getContext('2d');
    }
    if (!ctx) return;

    let aX = -0.42, aY = 0.65;
    let dragging = false, lx = 0, ly = 0;

    canvas.addEventListener('mousedown', (e) => {
      dragging = true; lx = e.clientX; ly = e.clientY;
    });
    window.addEventListener('mousemove', (e) => {
      if (!dragging) return;
      aY += (e.clientX - lx) * 0.008;
      aX += (e.clientY - ly) * 0.008;
      lx = e.clientX; ly = e.clientY;
      draw2D();
    });
    window.addEventListener('mouseup', () => { dragging = false; });

    // Wheel zoom for 2D mode
    let zoomLevel = 1.0;
    canvas.addEventListener('wheel', (e) => {
      zoomLevel *= (e.deltaY > 0 ? 0.93 : 1.07);
      zoomLevel = Math.max(0.4, Math.min(2.5, zoomLevel));
      draw2D();
      e.preventDefault();
    }, { passive: false });

    function project2D(x, y, z, cx, cy) {
      const cosY = Math.cos(aY), sinY = Math.sin(aY);
      const x1 = x * cosY + z * sinY;
      const z1 = -x * sinY + z * cosY;

      const cosX = Math.cos(aX), sinX = Math.sin(aX);
      const y2 = y * cosX - z1 * sinX;
      const z2 = y * sinX + z1 * cosX;

      const scale = (270 / (310 + z2 * 0.35)) * zoomLevel;
      return { screenX: cx + x1 * scale, screenY: cy + y2 * scale, depth: z2 };
    }

    function draw2D() {
      if (!cubeData || !canvas) return;
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const w = canvas.clientWidth || 800;
      const h = canvas.clientHeight || 480;

      canvas.width = w * dpr;
      canvas.height = h * dpr;

      ctx.save();
      ctx.scale(dpr, dpr);
      ctx.clearRect(0, 0, w, h);
      ctx.fillStyle = '#f8fafc';
      ctx.fillRect(0, 0, w, h);

      const cx = w / 2, cy = h / 2 + 10;
      const xLabels = cubeData.x_labels || [];
      const yLabels = cubeData.y_labels || [];
      const zLabels = cubeData.z_labels || [];

      const nx = Math.max(xLabels.length, 1);
      const ny = Math.max(yLabels.length, 1);
      const nz = Math.max(zLabels.length, 1);
      const spacing = 36;

      const halfX = ((nx - 1) * spacing) / 2;
      const halfY = ((ny - 1) * spacing) / 2;
      const halfZ = ((nz - 1) * spacing) / 2;

      const cells = [];
      const categoryMap = cubeData.category_map || {};

      xLabels.forEach((x, xi) => {
        yLabels.forEach((y, yi) => {
          zLabels.forEach((z, zi) => {
            const match = cubeData.cells ? cubeData.cells.find(c => c.x === x && c.y === y && c.z === z) : null;
            const val = match ? match.v : 0;
            const cat = match ? (match.cat || categoryMap[x] || 'Antibiotics') : (categoryMap[x] || 'Antibiotics');

            const px = xi * spacing - halfX;
            const py = yi * spacing - halfY;
            const pz = zi * spacing - halfZ;
            const proj = project2D(px, py, pz, cx, cy);

            cells.push({ x, y, z, val, cat, proj, px, py, pz });
          });
        });
      });

      // Depth sort (furthest to nearest)
      cells.sort((a, b) => b.proj.depth - a.proj.depth);

      // Render 3D Voxels
      const catColors = {
        'Antibiotics': '#0d9488',
        'Analgesics & Antipyretics': '#2563eb',
        'Antidiabetic': '#7c3aed',
        'Hormone Preparations': '#ea580c'
      };

      cells.forEach(c => {
        const hs = 11;
        // Project front and back vertices for isometric cube rendering
        const pTop0 = project2D(c.px - hs, c.py + hs, c.pz - hs, cx, cy);
        const pTop1 = project2D(c.px + hs, c.py + hs, c.pz - hs, cx, cy);
        const pTop2 = project2D(c.px + hs, c.py + hs, c.pz + hs, cx, cy);
        const pTop3 = project2D(c.px - hs, c.py + hs, c.pz + hs, cx, cy);

        const pBot0 = project2D(c.px - hs, c.py - hs, c.pz + hs, cx, cy);
        const pBot1 = project2D(c.px + hs, c.py - hs, c.pz + hs, cx, cy);

        const baseColor = catColors[c.cat] || '#0d9488';

        // Front Face
        ctx.beginPath();
        ctx.moveTo(pTop3.screenX, pTop3.screenY);
        ctx.lineTo(pTop2.screenX, pTop2.screenY);
        ctx.lineTo(pBot1.screenX, pBot1.screenY);
        ctx.lineTo(pBot0.screenX, pBot0.screenY);
        ctx.closePath();
        ctx.fillStyle = baseColor;
        ctx.globalAlpha = c.val > 0 ? 0.85 : 0.25;
        ctx.fill();
        ctx.strokeStyle = '#0f172a';
        ctx.lineWidth = 0.8;
        ctx.stroke();

        // Top Face
        ctx.beginPath();
        ctx.moveTo(pTop0.screenX, pTop0.screenY);
        ctx.lineTo(pTop1.screenX, pTop1.screenY);
        ctx.lineTo(pTop2.screenX, pTop2.screenY);
        ctx.lineTo(pTop3.screenX, pTop3.screenY);
        ctx.closePath();
        ctx.fillStyle = baseColor;
        ctx.globalAlpha = c.val > 0 ? 0.95 : 0.35;
        ctx.fill();
        ctx.stroke();

        ctx.globalAlpha = 1.0;
      });

      // 3D Outer Wireframe Cage
      const minX = -halfX - 16, maxX = halfX + 16;
      const minY = -halfY - 16, maxY = halfY + 16;
      const minZ = -halfZ - 16, maxZ = halfZ + 16;

      const corners = [
        project2D(minX, minY, minZ, cx, cy),
        project2D(maxX, minY, minZ, cx, cy),
        project2D(maxX, maxY, minZ, cx, cy),
        project2D(minX, maxY, minZ, cx, cy),
        project2D(minX, minY, maxZ, cx, cy),
        project2D(maxX, minY, maxZ, cx, cy),
        project2D(maxX, maxY, maxZ, cx, cy),
        project2D(minX, maxY, maxZ, cx, cy)
      ];

      const edges = [
        [0,1],[1,2],[2,3],[3,0],
        [4,5],[5,6],[6,7],[7,4],
        [0,4],[1,5],[2,6],[3,7]
      ];

      ctx.strokeStyle = '#94a3b8';
      ctx.lineWidth = 1.2;
      ctx.setLineDash([4, 4]);
      edges.forEach(([i, j]) => {
        ctx.beginPath();
        ctx.moveTo(corners[i].screenX, corners[i].screenY);
        ctx.lineTo(corners[j].screenX, corners[j].screenY);
        ctx.stroke();
      });
      ctx.setLineDash([]);

      ctx.restore();
    }

    window.render2DCubeCanvas = function(data) {
      cubeData = data;
      draw2D();
    };

    if (cubeData) {
      draw2D();
    }
  }

})();
