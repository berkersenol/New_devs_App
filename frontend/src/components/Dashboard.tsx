import React, { useEffect, useState } from "react";
import { RevenueSummary } from "./RevenueSummary";
import { SecureAPI } from "../lib/secureApi";

interface Property {
  id: string;
  name: string;
  timezone?: string;
}

// Reporting periods offered in the selector ("" = all time).
const PERIODS = [
  { value: "", label: "All time" },
  { value: "2024-01", label: "January 2024" },
  { value: "2024-02", label: "February 2024" },
  { value: "2024-03", label: "March 2024" },
  { value: "2024-04", label: "April 2024" },
];

const Dashboard: React.FC = () => {
  // Properties are loaded per tenant from the API instead of a hardcoded list
  // that showed every client's properties to everyone.
  const [properties, setProperties] = useState<Property[]>([]);
  const [selectedProperty, setSelectedProperty] = useState<string>("");
  const [period, setPeriod] = useState<string>("");
  const [loadError, setLoadError] = useState("");

  useEffect(() => {
    let cancelled = false;
    SecureAPI.getDashboardProperties()
      .then((res: { properties: Property[] }) => {
        if (cancelled) return;
        const list = res?.properties ?? [];
        setProperties(list);
        setSelectedProperty(list[0]?.id ?? "");
      })
      .catch((err: unknown) => {
        console.error(err);
        if (!cancelled) setLoadError("Failed to load properties");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const [year, month] = period ? period.split("-").map(Number) : [undefined, undefined];
  const selected = properties.find((p) => p.id === selectedProperty);

  return (
    <div className="p-4 lg:p-6 min-h-full">
      <div className="max-w-7xl mx-auto">
        <h1 className="text-2xl font-bold mb-6 text-gray-900">Property Management Dashboard</h1>

        <div className="bg-white rounded-lg shadow-sm border border-gray-200 p-4 lg:p-6">
          <div className="mb-6">
            <div className="flex flex-col sm:flex-row sm:justify-between sm:items-start gap-4">
              <div>
                <h2 className="text-lg lg:text-xl font-medium text-gray-900 mb-2">Revenue Overview</h2>
                <p className="text-sm lg:text-base text-gray-600">
                  Monthly performance insights for your properties
                </p>
                {selected?.timezone && (
                  <p className="text-xs text-gray-500 mt-1">Months are calculated in the property's local time ({selected.timezone}).</p>
                )}
              </div>

              <div className="flex flex-col sm:flex-row gap-4">
                {/* Period Selector */}
                <div className="flex flex-col sm:items-end">
                  <label className="text-xs font-medium text-gray-700 mb-1">Period</label>
                  <select
                    value={period}
                    onChange={(e) => setPeriod(e.target.value)}
                    className="block w-full sm:w-auto min-w-[160px] px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-sm"
                  >
                    {PERIODS.map((p) => (
                      <option key={p.value} value={p.value}>
                        {p.label}
                      </option>
                    ))}
                  </select>
                </div>

                {/* Property Selector */}
                <div className="flex flex-col sm:items-end">
                  <label className="text-xs font-medium text-gray-700 mb-1">Select Property</label>
                  <select
                    value={selectedProperty}
                    onChange={(e) => setSelectedProperty(e.target.value)}
                    disabled={properties.length === 0}
                    className="block w-full sm:w-auto min-w-[200px] px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-blue-500 focus:border-blue-500 text-sm"
                  >
                    {properties.map((property) => (
                      <option key={property.id} value={property.id}>
                        {property.name}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
            </div>
          </div>

          <div className="space-y-6">
            {loadError && <div className="p-4 text-red-500 bg-red-50 rounded-lg">{loadError}</div>}
            {selectedProperty && (
              <RevenueSummary propertyId={selectedProperty} month={month} year={year} />
            )}
          </div>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
