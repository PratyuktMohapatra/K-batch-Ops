import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card } from "@/components/ui/card";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

interface AutomationFormData {
  clientId: string;
  frequency: string;
  batchId: string;
}

export const AutomationPanel = () => {
  const [formData, setFormData] = useState<AutomationFormData>({
    clientId: "",
    frequency: "",
    batchId: "",
  });
  const [response, setResponse] = useState<string>("");
  const [isLoadingSingle, setIsLoadingSingle] = useState(false);
  const [isLoadingMultiple, setIsLoadingMultiple] = useState(false);

  const apiBaseUrl = import.meta.env.VITE_API_BASE_URL || "http://192.168.95.29:5000";
  const apiBaseUrlMultiple = import.meta.env.VITE_API_BASE_URL_MULTIPLE || "http://192.168.95.29:5001";

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setFormData({
      ...formData,
      [e.target.name]: e.target.value,
    });
  };

  const handleRunAutomation = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsLoadingSingle(true);
    setResponse("");

    try {
      const res = await fetch(`${apiBaseUrl}/run-automation`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          client_id: formData.clientId,
          frequency: formData.frequency,
          batch_id: formData.batchId,
        }),
      });

      const data = await res.json();
      setResponse(JSON.stringify(data, null, 2));

      if (res.ok) {
        toast.success("Automation triggered successfully");
      } else {
        toast.error("Failed to trigger automation");
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : "Unknown error occurred";
      setResponse(JSON.stringify({ error: errorMessage }, null, 2));
      toast.error("Failed to connect to API");
    } finally {
      setIsLoadingSingle(false);
    }
  };

  const handleTriggerMultiple = async () => {
    setIsLoadingMultiple(true);
    setResponse("");

    try {
      const res = await fetch(`${apiBaseUrlMultiple}/trigger-multiple`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
      });

      const data = await res.json();
      setResponse(JSON.stringify(data, null, 2));

      if (res.ok) {
        toast.success("Multiple automations triggered successfully");
      } else {
        toast.error("Failed to trigger multiple automations");
      }
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : "Unknown error occurred";
      setResponse(JSON.stringify({ error: errorMessage }, null, 2));
      toast.error("Failed to connect to API");
    } finally {
      setIsLoadingMultiple(false);
    }
  };

  return (
    <div className="min-h-screen p-4 sm:p-6 lg:p-8">
      <div className="text-center space-y-2 mb-8">
        <h1 className="text-4xl sm:text-5xl font-bold tracking-tight">
          K-Batch-Ops
        </h1>
        <p className="text-muted-foreground text-sm uppercase tracking-widest">
          KUBERNETES NATIVE AUTOMATION
        </p>
      </div>

      <div className="grid lg:grid-cols-[1.6fr_3.4fr] gap-6 max-w-7xl mx-auto items-stretch">
        {/* Left Side - Input Form */}
        <Card className="p-6 sm:p-8 backdrop-blur-sm border-border/50 h-full flex flex-col">
          <form onSubmit={handleRunAutomation} className="space-y-6">
            <div className="space-y-4">
              <div className="space-y-2">
                <Label htmlFor="clientId" className="text-xs uppercase tracking-wider 
      text-muted-foreground">
                  Client ID
                </Label>
                <Input
                  id="clientId"
                  name="clientId"
                  type="text"
                  value={formData.clientId}
                  onChange={handleInputChange}
                  required
                  className="bg-background border-border/50 focus:border-primary transition-colors"
                  placeholder="Enter client identifier"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="frequency" className="text-xs uppercase tracking-wider 
      text-muted-foreground">
                  Frequency
                </Label>
                <Input
                  id="frequency"
                  name="frequency"
                  type="text"
                  value={formData.frequency}
                  onChange={handleInputChange}
                  required
                  className="bg-background border-border/50 focus:border-primary transition-colors"
                  placeholder="Enter execution frequency"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="batchId" className="text-xs uppercase tracking-wider 
      text-muted-foreground">
                  Batch ID
                </Label>
                <Input
                  id="batchId"
                  name="batchId"
                  type="text"
                  value={formData.batchId}
                  onChange={handleInputChange}
                  required
                  className="bg-background border-border/50 focus:border-primary transition-colors"
                  placeholder="Enter batch identifier"
                />
              </div>
            </div>

            <div className="flex flex-col sm:flex-row gap-3">
              <Button
                type="submit"
                disabled={isLoadingSingle}
                className="flex-1 h-12 text-base font-semibold"
              >
                {isLoadingSingle ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Processing...
                  </>
                ) : (
                  "Run Automation"
                )}
              </Button>

              <Button
                type="button"
                variant="accent"
                onClick={handleTriggerMultiple}
                disabled={isLoadingMultiple}
                className="flex-1 h-12 text-base font-semibold"
              >
                {isLoadingMultiple ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    Processing...
                  </>
                ) : (
                  "Trigger Multiple Automations"
                )}
              </Button>
            </div>
          </form>
        </Card>

        {/* Right Side - System Response */}
        <Card className="p-6 backdrop-blur-sm border-border/50 h-full flex flex-col">
          <div className="space-y-3 h-full flex flex-col">
            <h2 className="text-xs uppercase tracking-widest text-accent font-semibold">
              System Response
            </h2>
            {response ? (
              <pre className="bg-background/50 text-foreground p-4 rounded-lg overflow-auto text-sm 
      border border-border/30 font-mono flex-1">
                {response}
              </pre>
            ) : (
              <div className="bg-background/50 text-muted-foreground/50 p-4 rounded-lg text-sm border 
      border-border/30 flex-1 flex items-center justify-center">
                Awaiting response...
              </div>
            )}
          </div>
        </Card>
      </div>

      <div className="text-center mt-8">
        <p className="text-xs text-muted-foreground uppercase tracking-wider">
          System created by Pratyukt
        </p>
      </div>
    </div>
  );
};
