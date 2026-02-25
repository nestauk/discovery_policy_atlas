# Container Type

AWS provide several ways of managing container runtimes and compute:

* AWS Fargate
    * Managed containers-as-a-service: simply request CPU and RAM, and the container just runs.
    * Pros: Very easy to work with. No server maintenance of any kind. Most like managed services like Railway.
    * Cons: Most expensive AWS option, processor-for-processor.
* AWS ECS Clusters
    * Manage a fleet of EC2 instances that provide compute. AWS provide a managed AMI (Amazon Machine Image) that is optimized for this purpose.
    * Pros: Easy to work with, as most EC2 logic can be handled automatically. Managed AMIs work well. Cheaper than Fargate.
    * Cons: 'Easy' is not 'Very Easy'. Some manual work is required, but this is mostly managed by AWS and the CDK code.
* AWS Managed EKS
    * A managed Kubernetes cluster. AWS provide compute under the hood.
    * Won't be used - is just Fargate, but worse.
* AWS Managed EKS on EC2
    * A managed Kubernetes cluster, but uses EC2 instances we provision under the hood.
    * Only really an option when we scale out to monumental size, as it has operational and cost overhead, but allows for the increased flexibility of Kubernetes.
    * Probably overkill.

I'm working with Fargate, to start, with the option to port to a managed ECS cluster should cost exceed desired amounts.

# Supabase

We're going self-managed; it's a big enough job to get it deployed that I'm using an EC2 instance running Docker itself so I can use the true compose files provided by Supabase themselves.