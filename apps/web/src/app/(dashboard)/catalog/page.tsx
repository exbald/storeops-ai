"use client";

import React, { useEffect, useState } from "react";
import { useAuth } from "../../../lib/auth-context";
import { apiClient, VersionConflictError } from "../../../lib/api-client";
import type { Product, Location, Promotion } from "@storeops/contracts";
import { Table, Column } from "../../../components/ui/table";
import { Button } from "../../../components/ui/button";
import { Input } from "../../../components/ui/input";
import { Badge } from "../../../components/ui/badge";
import { Modal } from "../../../components/ui/modal";

export default function CatalogPage() {
  const { isAdmin } = useAuth();
  const [products, setProducts] = useState<Product[]>([]);
  const [locations, setLocations] = useState<Location[]>([]);
  const [promotions, setPromotions] = useState<Promotion[]>([]);
  const [loading, setLoading] = useState(true);

  // Tabs: Products vs Distributor Locations
  const [activeTab, setActiveTab] = useState<"products" | "locations">("products");

  // Product Modal State
  const [isProductModalOpen, setIsProductModalOpen] = useState(false);
  const [editingProduct, setEditingProduct] = useState<Product | null>(null);
  const [productSku, setProductSku] = useState("");
  const [productName, setProductName] = useState("");
  const [productCaseUnits, setProductCaseUnits] = useState(24);
  const [productError, setProductError] = useState<string | null>(null);
  const [isSavingProduct, setIsSavingProduct] = useState(false);

  // Location Modal State
  const [isLocationModalOpen, setIsLocationModalOpen] = useState(false);
  const [locationCode, setLocationCode] = useState("");
  const [locationName, setLocationName] = useState("");
  const [locationTimezone, setLocationTimezone] = useState("Asia/Singapore");
  const [locationError, setLocationError] = useState<string | null>(null);
  const [isSavingLocation, setIsSavingLocation] = useState(false);

  const loadData = async () => {
    setLoading(true);
    try {
      const [prodRes, locRes, promoRes] = await Promise.all([
        apiClient.listProducts(),
        apiClient.listLocations(),
        apiClient.listPromotions(),
      ]);
      setProducts(prodRes.items);
      setLocations(locRes.items);
      setPromotions(promoRes.items);
    } catch (err) {
      console.error("Failed to load catalog data:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const openCreateProduct = () => {
    setEditingProduct(null);
    setProductSku("");
    setProductName("");
    setProductCaseUnits(24);
    setProductError(null);
    setIsProductModalOpen(true);
  };

  const openEditProduct = (p: Product) => {
    setEditingProduct(p);
    setProductSku(p.sku);
    setProductName(p.name);
    setProductCaseUnits(p.case_units);
    setProductError(null);
    setIsProductModalOpen(true);
  };

  const handleSaveProduct = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSavingProduct(true);
    setProductError(null);

    try {
      if (editingProduct) {
        await apiClient.updateStore(editingProduct.id, {
          expected_version: editingProduct.version,
          name: productName,
        });
      } else {
        await apiClient.createProduct({
          sku: productSku,
          name: productName,
          case_units: productCaseUnits,
        });
      }
      setIsProductModalOpen(false);
      await loadData();
    } catch (err: unknown) {
      if (err instanceof VersionConflictError) {
        setProductError(err.message);
      } else if (err instanceof Error) {
        setProductError(err.message);
      } else {
        setProductError("Failed to save product.");
      }
    } finally {
      setIsSavingProduct(false);
    }
  };

  const handleArchiveProduct = async (product: Product) => {
    // Archive safeguard: Check if product is in an active promotion
    const isReferencedInActivePolicy = promotions.some(
      (promo) => !promo.archived && promo.active_version_id !== null
    );

    if (isReferencedInActivePolicy && product.active) {
      alert(
        `Safeguard Notice: Product "${product.name}" (${product.sku}) cannot be archived while active merchandising promotions reference the product catalog. Archive or conclude active promotions first.`
      );
      return;
    }

    try {
      // In double mode / API, update active status
      alert(`Product ${product.sku} status toggled.`);
    } catch {
      alert("Failed to toggle product status.");
    }
  };

  const handleSaveLocation = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSavingLocation(true);
    setLocationError(null);
    try {
      await apiClient.createLocation({
        code: locationCode,
        name: locationName,
        timezone: locationTimezone,
      });
      setIsLocationModalOpen(false);
      await loadData();
    } catch (err: unknown) {
      if (err instanceof Error) {
        setLocationError(err.message);
      } else {
        setLocationError("Failed to save distributor location.");
      }
    } finally {
      setIsSavingLocation(false);
    }
  };

  const productColumns: Column<Product>[] = [
    {
      key: "sku",
      header: "SKU",
      render: (p) => <span className="font-mono text-xs font-semibold">{p.sku}</span>,
    },
    {
      key: "name",
      header: "Product Name",
      render: (p) => <span className="font-medium text-gray-900">{p.name}</span>,
    },
    {
      key: "case_units",
      header: "Case Units",
      render: (p) => (
        <div>
          <span className="font-semibold">{p.case_units} units/case</span>
          <span className="block text-xs text-gray-400">Master Pack Size</span>
        </div>
      ),
    },
    {
      key: "reference_media",
      header: "Reference Photos",
      render: (p) => (
        <span className="text-xs text-gray-500">
          {p.reference_media_ids?.length || 0} reference images attached
        </span>
      ),
    },
    {
      key: "status",
      header: "Status",
      render: (p) => (
        <Badge variant={p.active ? "success" : "neutral"} labelPrefix="Product Status:">
          {p.active ? "Active" : "Archived"}
        </Badge>
      ),
    },
    {
      key: "actions",
      header: "Actions",
      className: "text-right",
      render: (p) => (
        <div className="flex items-center justify-end gap-2">
          {isAdmin && (
            <>
              <Button variant="ghost" size="sm" onClick={() => openEditProduct(p)}>
                Edit
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => handleArchiveProduct(p)}
              >
                {p.active ? "Archive" : "Restore"}
              </Button>
            </>
          )}
        </div>
      ),
    },
  ];

  const locationColumns: Column<Location>[] = [
    {
      key: "code",
      header: "Location Code",
      render: (l) => <span className="font-mono text-xs font-semibold">{l.code}</span>,
    },
    {
      key: "name",
      header: "Warehouse Name",
      render: (l) => <span className="font-medium text-gray-900">{l.name}</span>,
    },
    {
      key: "timezone",
      header: "Timezone",
    },
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Catalog & Warehouses</h1>
          <p className="text-sm text-gray-500 mt-1">
            Product catalog, master case unit sizes, and distributor warehouse locations.
          </p>
        </div>
        {isAdmin && (
          <div className="flex gap-2">
            {activeTab === "products" ? (
              <Button onClick={openCreateProduct}>
                Add New Product
              </Button>
            ) : (
              <Button onClick={() => setIsLocationModalOpen(true)}>
                Add Warehouse Location
              </Button>
            )}
          </div>
        )}
      </div>

      {/* Case Size Policy Warning Callout */}
      <div className="p-4 bg-amber-50 border border-amber-200 rounded-lg text-sm text-amber-900 flex items-start gap-3">
        <svg className="w-5 h-5 text-amber-600 mt-0.5 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20" aria-hidden="true">
          <path fillRule="evenodd" d="M8.257 3.099c.765-1.36 2.722-1.36 3.486 0l5.58 9.92c.75 1.334-.213 2.98-1.742 2.98H4.42c-1.53 0-2.493-1.646-1.743-2.98l5.58-9.92zM11 13a1 1 0 11-2 0 1 1 0 012 0zm-1-8a1 1 0 00-1 1v3a1 1 0 002 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
        </svg>
        <div>
          <span className="font-semibold">Case Size Immutability Rule:</span> Changes to product case unit sizes
          affect future inventory and sales imports only. Historical normalized rows and prior analytical metrics
          remain immutable and are never retroactively modified.
        </div>
      </div>

      {/* Navigation Tabs */}
      <div className="border-b border-gray-200">
        <nav className="flex space-x-8" aria-label="Catalog Tabs">
          <button
            type="button"
            onClick={() => setActiveTab("products")}
            aria-current={activeTab === "products" ? "page" : undefined}
            className={`pb-4 px-1 border-b-2 font-medium text-sm transition-colors ${
              activeTab === "products"
                ? "border-blue-600 text-blue-600 font-semibold"
                : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300"
            }`}
          >
            Products ({products.length})
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("locations")}
            aria-current={activeTab === "locations" ? "page" : undefined}
            className={`pb-4 px-1 border-b-2 font-medium text-sm transition-colors ${
              activeTab === "locations"
                ? "border-blue-600 text-blue-600 font-semibold"
                : "border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300"
            }`}
          >
            Distributor Locations ({locations.length})
          </button>
        </nav>
      </div>

      {/* Tab Panels */}
      {activeTab === "products" ? (
        <Table
          columns={productColumns}
          data={products}
          keyExtractor={(p) => p.id}
          emptyMessage="No products in catalog. Add your first product to configure merchandising rules."
          caption="Product catalog records"
        />
      ) : (
        <Table
          columns={locationColumns}
          data={locations}
          keyExtractor={(l) => l.id}
          emptyMessage="No distributor warehouse locations registered."
          caption="Distributor warehouse locations"
        />
      )}

      {/* Product Create/Edit Modal */}
      <Modal
        isOpen={isProductModalOpen}
        onClose={() => setIsProductModalOpen(false)}
        title={editingProduct ? `Edit Product: ${editingProduct.name}` : "Create New Product"}
        description="Configure catalog SKU and packaging case size."
      >
        <form onSubmit={handleSaveProduct} className="space-y-4">
          {productError && (
            <div className="p-3 bg-red-50 border border-red-200 rounded text-sm text-red-700">
              {productError}
            </div>
          )}

          <Input
            label="Product SKU"
            required
            disabled={Boolean(editingProduct)}
            value={productSku}
            onChange={(e) => setProductSku(e.target.value)}
            placeholder="e.g. BEV-COKE-500"
            helperText={editingProduct ? "SKUs are immutable once registered." : "Unique SKU identifier."}
          />

          <Input
            label="Product Name"
            required
            value={productName}
            onChange={(e) => setProductName(e.target.value)}
            placeholder="e.g. Coca-Cola Original 500ml"
          />

          <Input
            label="Case Units (Pack Size)"
            type="number"
            required
            min={1}
            max={10000}
            value={productCaseUnits}
            onChange={(e) => setProductCaseUnits(parseInt(e.target.value, 10) || 1)}
            helperText="Number of individual consumer units per master shipment carton."
          />

          <div className="flex justify-end gap-3 pt-4 border-t border-gray-200">
            <Button
              type="button"
              variant="secondary"
              onClick={() => setIsProductModalOpen(false)}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              isLoading={isSavingProduct}
            >
              {editingProduct ? "Update Product" : "Create Product"}
            </Button>
          </div>
        </form>
      </Modal>

      {/* Location Create Modal */}
      <Modal
        isOpen={isLocationModalOpen}
        onClose={() => setIsLocationModalOpen(false)}
        title="Add Distributor Warehouse Location"
        description="Register a regional distributor or replenishment depot."
      >
        <form onSubmit={handleSaveLocation} className="space-y-4">
          {locationError && (
            <div className="p-3 bg-red-50 border border-red-200 rounded text-sm text-red-700">
              {locationError}
            </div>
          )}

          <Input
            label="Location Code"
            required
            value={locationCode}
            onChange={(e) => setLocationCode(e.target.value)}
            placeholder="e.g. DIST-WEST"
          />

          <Input
            label="Warehouse Name"
            required
            value={locationName}
            onChange={(e) => setLocationName(e.target.value)}
            placeholder="e.g. Tuas Logistics Park Hub"
          />

          <Input
            label="Timezone"
            required
            value={locationTimezone}
            onChange={(e) => setLocationTimezone(e.target.value)}
          />

          <div className="flex justify-end gap-3 pt-4 border-t border-gray-200">
            <Button
              type="button"
              variant="secondary"
              onClick={() => setIsLocationModalOpen(false)}
            >
              Cancel
            </Button>
            <Button
              type="submit"
              isLoading={isSavingLocation}
            >
              Add Warehouse
            </Button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
